# install-kev-task.ps1
# Register Kev as a Scheduled Task `KevServer` on peecee: runs run-kev-serve.cmd at startup
# as the installing user (bare name: the DOMAIN\user form fails SID mapping here), S4U logon (no stored
# password, no interactive desktop), no time limit, auto-restart. Same pattern as the
# ollama task in ../ollama/install-ollama-service.ps1. Run from an elevated PowerShell.
$ErrorActionPreference = 'Stop'
$TaskName = 'KevServer'
$Wrapper  = Join-Path $env:USERPROFILE 'kev\run-kev-serve.cmd'
if (-not (Test-Path $Wrapper)) { throw "missing $Wrapper (scp it from infra hosts/peecee/config/kev/)" }
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action    = New-ScheduledTaskAction  -Execute 'cmd.exe' -Argument "/c `"$Wrapper`""
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Registered and started '$TaskName' (user, S4U, AtStartup; log: $env:USERPROFILE\kev\logs\server.log)"
Write-Host "Wait for 'serving jaredpalmer/kev-4b' in the log, then: Invoke-RestMethod http://127.0.0.1:8008/v1/models"
