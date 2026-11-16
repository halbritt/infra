# install-whisper-task.ps1
# Register whisper-server as Scheduled Task `WhisperServer` (user, S4U, AtStartup, no time
# limit, auto-restart; same pattern as ../kev/install-kev-task.ps1) and open TCP 8910 to the
# LAN and the tailnet only. Run from an elevated PowerShell.
$ErrorActionPreference = 'Stop'
$TaskName = 'WhisperServer'
$Wrapper  = Join-Path $env:USERPROFILE 'whisper\run-whisper-serve.cmd'
if (-not (Test-Path $Wrapper)) { throw "missing $Wrapper (scp it from infra hosts/peecee/config/whisper/)" }

$RuleName = 'whisper-server 8910 (LAN + tailnet)'
Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort 8910 -RemoteAddress '192.168.1.0/24','100.64.0.0/10' -Profile Any | Out-Null

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action    = New-ScheduledTaskAction  -Execute 'cmd.exe' -Argument "/c `"$Wrapper`""
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Registered and started '$TaskName' (log: $env:USERPROFILE\whisper\logs\server.log)"
