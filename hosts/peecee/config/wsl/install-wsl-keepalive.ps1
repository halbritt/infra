# Run on peecee in an elevated PowerShell. Idempotent.
# - installs .wslconfig for user halbr
# - creates Scheduled Task WslKeepalive (at startup, as halbr) that boots the Ubuntu distro
#   so sshd on :2222 comes up without a login session
# - opens Windows Firewall + Hyper-V firewall for TCP 2222 (mirrored networking)
$ErrorActionPreference = 'Stop'
$src = "C:\Users\halbr\wsl-setup"
Copy-Item "$src\.wslconfig" "C:\Users\halbr\.wslconfig" -Force

$action  = New-ScheduledTaskAction -Execute 'C:\Windows\System32\wsl.exe' -Argument '-d Ubuntu --exec /bin/sh -c "while true; do sleep 3600; done"'
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId 'halbr' -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName 'WslKeepalive' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

if (-not (Get-NetFirewallRule -DisplayName 'WSL sshd 2222' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName 'WSL sshd 2222' -Direction Inbound -Protocol TCP -LocalPort 2222 -Action Allow | Out-Null
}
# Hyper-V firewall gates inbound to mirrored-mode WSL; allow 2222 for the WSL VM creator id.
$wslVm = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'
if (-not (Get-NetFirewallHyperVRule -Name 'WSL-sshd-2222' -ErrorAction SilentlyContinue)) {
  New-NetFirewallHyperVRule -Name 'WSL-sshd-2222' -DisplayName 'WSL sshd 2222' -Direction Inbound -VMCreatorId $wslVm -Protocol TCP -LocalPorts 2222 -Action Allow | Out-Null
}
Write-Host "installed: .wslconfig, task WslKeepalive, firewall rules"
