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
