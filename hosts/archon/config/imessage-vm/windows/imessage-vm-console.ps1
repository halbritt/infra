# imessage-vm private console for Windows (installed on peecee as
# %USERPROFILE%\Desktop\imessage-vm-console.ps1 with a .cmd shortcut).
# SSH-tunnels archon's QEMU VNC socket to 127.0.0.1:5901 and opens TigerVNC.
# Requires the `archon` alias in ~/.ssh/config and peecee's forwarding-only key on archon.
$ErrorActionPreference = 'Stop'
$viewer = 'C:\Program Files\TigerVNC\vncviewer.exe'
$tunnel = Start-Process -PassThru -WindowStyle Hidden ssh -ArgumentList @(
  '-N', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
  '-L', '127.0.0.1:5901:/run/imessage-vm/vnc.sock', 'archon')
try {
  Start-Sleep -Seconds 3
  if ($tunnel.HasExited) { throw "SSH tunnel to archon failed (exit $($tunnel.ExitCode))" }
  Start-Process -Wait $viewer -ArgumentList 'localhost::5901'
} finally {
  if (-not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id }
}
