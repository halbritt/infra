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

The deck sits on the monitor's downstream USB hub (a Fresco Logic
`1D5C:5801` hub, next to the monitor's own `0451:ACE1` device on archon). At
install time that hub was attached to **archon**, even though archon's
DisplayPort output was in DPMS Off. Peecee is also connected over USB: it sees
the monitor's control device (`043E:9A39`, serial `601INZY73733`) through
motherboard hub port 10. The downstream ports did not follow the input switch.
Check the monitor's USB upstream / KVM selection. Verify with:

```powershell
Get-PnpDevice -PresentOnly | Where-Object InstanceId -match 'VID_0FD9'
```
