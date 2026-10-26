# Peecee motherboard BIOS

## Owner-authorized update to 4601 — prepared 2026-10-26

The owner requested updating BIOS after GPU probe captures showed an aggregate
ASUS console arrangement that the generic unlock profile generator rejects.
Firmware age could affect this layout; no release note establishes the update
as a fix. See [GPU investigation](../gpu-unlock/README.md).

Live board: ASUSTeK ROG STRIX Z690-I GAMING WIFI. Installed BIOS before update:
3501, SMBIOS build date 2024-04-18 (ASUS release date 2024-04-24).
Target: 4601, ASUS release date 2026-09-29. Intel ME is also updated to
16.1.40.2765; ASUS says ME remains updated after a BIOS rollback.

### Prepared update

- Official download:
  `https://dlcdnets.asus.com/pub/ASUS/mb/BIOS/ROG-STRIX-Z690-I-GAMING-WIFI-ASUS-4601.zip`.
- Download SHA-256 matches the ASUS support page:
  `a177845de9592a6f72fa450087f8cf9dbe94a5e14ea6b5a125aa6414c20b1f0e`.
- Extracted and staged `E:\ROG-STRIX-Z690-I-GAMING-WIFI-ASUS-4601.CAP`,
  33,558,528 bytes, SHA-256
  `8fd44f642c316429d346a6ce8e49e67e02c9559c502060d311b6623c1d341f06`.
- Verified the copied CAP hash on peecee and rechecked Lexar USB/FAT32 identity.
- BitLocker: C:, D:, E: fully decrypted, protection off, encryption 0 percent;
  no suspension or recovery-key access needed.
- Saved original archive and extracted CAP under proximal
  `~/.local/share/infra/evidence/peecee-bios-4601-20261026/`.
- Preserved post-iGPU/pre-BIOS probe evidence on USB in
  `E:\RTX3090-UNLOCK\capture-bios3501-igpu-20261026\` after checking all
  53 file hashes. Earlier capture-before-igpu folder remains. New firmware
  captures must not be mixed with either old set.

[Package manifest](4601-manifest.json) records artifact sizes and hashes.
Use the built-in ASUS EZ Flash 3 utility: BIOS Advanced Mode (F7) > Tool >
ASUS EZ Flash 3 > Lexar USB > the CAP file above. Confirm the displayed board
and version 4601, then start the update and allow all update/restart phases to
finish without interrupting power. This physical firmware UI is not controlled
by the SSH session. No generic third-party flash utility was used.

The owner authorized the update and necessary reboot. The remote command
`shutdown.exe /r /fw /t 0` returned success, requesting the next boot into
firmware setup without forced application termination. The final firmware-screen
selection and flash completion remain unverified. On return to Windows, verify
SMBIOS version4601 and device/service health. Recheck iGPU Multi-Monitor enabled
and Secure Boot disabled for the unsigned diagnostic probe, since an update can
reset settings. Then obtain fresh full-shutdown probe captures and analyze them
before any GPU unlock deployment. The existing generic probe still targets the
same Windows ESP; confirm that partition identity before reusing it.

Sources checked 2026-10-26:
[ASUS releases](https://www.asus.com/us/supportonly/rog%20strix%20z690-i%20gaming%20wifi/helpdesk_bios/),
[ASUS EZ Flash procedure](https://www.asus.com/global/support/faq/1012815/).

## Post-update live verification — 2026-10-26

After the owner's physical flash and return to Windows, SMBIOS reports **4601**.
Intel UHD Graphics 770 and RTX 3090 Ti both report OK. Secure Boot is disabled,
Windows ESP GUID is unchanged, and USB probe SHA-256 still matches the staged
binary. SSH and Tailscale services are running; OllamaServer and KevServer
Scheduled Tasks report Running. NVIDIA driver remains610.88; the card reported
35 C at inspection. GPU exporter was stopped at the initial check; started the
existing service and verified its tailnet metrics endpoint reports the RTX3090Ti.
No exporter configuration changed.

The owner reported that BIOS settings reset and POST halted for missing CPU fan
RPM. Cooling uses an Aquacomputer controller. Advised Monitor > Fan Speed
Monitor > CPU Fan Speed > Ignore for the unused CPU_FAN input, after confirming
pump/fans run; also restore iGPU Multi-Monitor, Secure Boot off and Windows Boot
Manager. Owner then reported the box back up. The exact fan setting was not
read back remotely. Preserve this cooling arrangement when planning future
BIOS resets; do not infer a failed pump from the unused motherboard RPM input.

A newly created complete USB probe capture was retrieved, but the owner has
been asked whether it was booted after the flash. File novelty alone does not
prove which firmware produced it. See GPU investigation for capture identity.

Follow-up: a subsequent owner-requested reboot produced DIAG01 with BIOS4601
known installed before reboot. That complete capture confirms the same firmware
console mismatch. The earlier DIAG00 chronology is no longer needed to establish
that4601 did not resolve it. See GPU investigation's confirmed4601 section.
