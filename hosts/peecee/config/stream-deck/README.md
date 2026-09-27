# Elgato Stream Deck

Installed 2026-09-26 at the owner's request for a **Stream Deck MK.2**
(USB `0FD9:0080`). The owner plugged it into the LG UltraFine monitor, which
peecee shares with archon.

## Install

```powershell
winget install --id Elgato.StreamDeck --exact --silent --accept-package-agreements --accept-source-agreements
```

- Package `Elgato.StreamDeck` 7.6.0.23012 (publisher Corsair Memory, Inc.).
  MSI from `edge.elgato.com`, and winget verified the installer hash.
  Dependency: `Microsoft.VCRedist.2015+.x64`.
- The app talks to the deck over standard HID and needs no separate kernel
  driver.
- Install path: `C:\Program Files\Elgato\StreamDeck\`. It also installs the
  Volume Controller plugin under `C:\Program Files\Elgato\Volume Controller\`.

## Startup entries added (`halbr` Run key)

| Name | Command |
| --- | --- |
| Stream Deck | `"C:\Program Files\Elgato\StreamDeck\StreamDeck.exe" --runinbk` |
| Volume Controller SD plugin | `C:\Program Files\Elgato\Volume Controller\ElgatoAudioControlServerWatcher.exe` |

No services or Scheduled Tasks were added.

## Launching from SSH

Installing from SSH started the Volume Controller in session 0. Those copies
were stopped. Both programs were then started in `halbr`'s desktop session
(session 1) with a temporary Interactive-logon Scheduled Task, which was
deleted afterwards. Use one task per program, because a task runs its actions
one after another and the Watcher never exits.

## Monitor USB routing

The LG 32U990A (UltraFine evo 6K) is shared by peecee and archon:

- **Archon:** Thunderbolt 5 upstream (its kernel logs Thunderbolt port 0:5).
- **Peecee:** DisplayPort video plus a USB link. Peecee sees the monitor's
  control device (`043E:9A39`, serial `601INZY73733`) through motherboard hub
  port 10.

The deck was first plugged into the monitor's **Thunderbolt 5 downstream**
(daisy-chain) port. It enumerated on archon behind a Fresco Logic `1D5C:5801`
hub, next to the monitor's `0451:ACE1` device. It stayed on archon while
archon's DisplayPort output was in DPMS Off. Toggling the OSD **USB Selection**
didn't disconnect that hub either. Archon's kernel logged no hub disconnect.
Conclusion: the Thunderbolt downstream port follows the Thunderbolt host, not
the monitor's KVM/USB Selection. Use the monitor's USB-C 3.2 downstream ports,
or peecee's own ports, for devices that belong to peecee.

The owner then moved the deck. At 2026-09-26 22:46, peecee enumerated it
(`USB\VID_0FD9&PID_0080\A00SA6102QCGR8`) through Genesys `05E3:0610` hubs
under root hub port 10. The Stream Deck app log reported `Device connected`,
firmware 1.02.000. Archon no longer listed it. Verify with:

```powershell
Get-PnpDevice -PresentOnly | Where-Object InstanceId -match 'VID_0FD9'
```
