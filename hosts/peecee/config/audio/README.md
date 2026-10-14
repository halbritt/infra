# Onboard audio on peecee

The ASUS ROG Strix Z690-I Gaming WiFi exposes its Realtek onboard audio as
`USB\VID_0B05&PID_1A20&MI_00`. The desired base driver is the signed ASUS
Realtek USB Audio `6.3.9600.2342` package (`RtDUsbAD_asus.inf`), the newest
audio package listed for this board on the [ASUS support page](https://www.asus.com/us/supportonly/rog%20strix%20z690-i%20gaming%20wifi/helpdesk_download/)
as checked on 2026-09-23. The newer `B6.3.9600.2342` package date is
2023-03-31; the `B` package disables the Sonic Studio 3 virtual mixer for
stability. The INF itself records driver version `6.3.9600.2342`.

The downloaded ASUS archive is
`C:\Users\halbr\Downloads\DRV_Audio_RTK_USB_CNT_DTSP_SP_W11_64_V6396002342_20230330B.zip`
(SHA-256 `7529558F2ED8171DFC283A1AED925915D555441B7ED5874722FC41D6E3031F49`).
The four base-driver files from `USBAud/Win64/` are staged at
`C:\ProgramData\Infra\audio\Realtek-USB-6.3.9600.2342\`.

To install or repair the base driver from an elevated PowerShell session:

```powershell
pnputil /add-driver 'C:\ProgramData\Infra\audio\Realtek-USB-6.3.9600.2342\RtDUsbAD_asus.inf' /install
```

Windows may require a reboot (exit code `3010`). Check the live binding with
`pnputil /enum-devices /instanceid "USB\VID_0B05&PID_1A20&MI_00\6&208CEBFE&0&0000" /drivers`;
the last segment of the instance ID may change after hardware enumeration.
The Realtek package should be installed and best ranked. The Microsoft
`usbaudio2.inf` remains available for rollback. The existing Realtek extension
driver and Windows audio services are separate from this base driver.

The ASUS archive also contains `install.bat`, which deletes DTS state, adds a
virtual audio device, installs optional apps, and creates an on-logon task.
Those effects are outside the base-driver repair and were not applied here.

## Live recheck — October 13, 2026

After the owner suspected another Windows Update regression, a read-only SSH
inspection found the same Realtek base driver `6.3.9600.2342` bound through
`oem94.inf`, with extension `oem45.inf` still present. `pnputil` reported
**Best Ranked / Installed** and device **Started**. Microsoft's newer
`usbaudio2.inf` version `10.0.26100.9549` was available but **Outranked**, not
bound to this device. PnP reported `OK` / `CM_PROB_NONE` for the Realtek device
and its SPDIF endpoint. `Audiosrv` and `AudioEndpointBuilder` were running.
The latest installed hotfix returned by `Get-HotFix` was `KB5121794`, October 10.

This establishes that the previous generic-driver replacement had not recurred.
It does not verify default output selection, volume/mute state, cable/speaker
state, or audible playback. No audio driver, service, or endpoint was changed.

### Follow-up: Chrome silent through WiiM Amp Ultra

The owner reported no sound after the driver recheck. Further live inspection
on October 13 found Chrome's interactive-session audio routed to Realtek USB
Audio, unmuted at 100%; the default console and multimedia output was SPDIF.
The format was stereo 24-bit/48 kHz. Thirty Windows endpoint-meter samples
contained a nonzero signal (peak 0.438). This proves a signal in the Windows
mixer, not optical transmission or audible output.

The WiiM Amp Ultra at `192.168.1.119` reported Optical input, volume 21, mute 0,
and playback status `stop`. Its duplicate HA integrations differed in playback
state, so the direct device API was used. A resume command returned `OK` without
changing `stop`. An Optical reselect request failed while the owner was
power-cycling the amplifier; the owner confirmed that the restart did not fix
sound and that the optical connection to peecee had been checked.

`pnputil /restart-device` on Realtek returned 3010 (reboot required). A System
Kernel-PnP event at 17:13:39 PDT identified `audiodg.exe` as blocking removal of
the device. Stopping `Audiosrv` and retrying the device restart then returned
50: the device was pending a reboot to complete the previous operation. The
service was restored in a finally block; `Audiosrv` and `AudioEndpointBuilder`
were running and the device still reported `OK` / `CM_PROB_NONE` afterwards.
A full PC reboot requires owner coordination because Windows apps will close.
This does not establish that Windows Update caused the silence or that the
optical link and amplifier are working. No driver package was replaced.

For future read-only per-app inspection, run the sound inventory in the logged-in
interactive Windows session: an SSH session alone did not expose Chrome's audio
session. Temporary NirSoft `svcl` / `SoundVolumeView` utilities were fetched from
nirsoft.net; temporary diagnostic scheduled tasks were removed after each use.
