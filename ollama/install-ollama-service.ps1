# install-ollama-service.ps1
# Swap the Ollama DESKTOP app for a headless, boot-start Ollama SERVER on peecee
# (Windows 11). Run on peecee in an elevated shell. Idempotent. Reversible via
# uninstall-ollama-service.ps1.
#
# Keeps the SAME port (11434), binds all interfaces (preserves LAN/tailscale reach),
# and uses the existing model store. Runs as a Scheduled Task under SYSTEM at boot
# (the sanctioned Windows approach in gpu-fleet's design — no NSSM, no extra software).

$ErrorActionPreference = 'Stop'

$OllamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
$ModelsDir = Join-Path $env:USERPROFILE '.ollama\models'
$TaskName  = 'OllamaServer'

if (-not (Test-Path $OllamaExe)) { throw "ollama.exe not found at $OllamaExe" }
Write-Host "ollama.exe : $OllamaExe"
Write-Host "models dir : $ModelsDir"

# 1. Machine-wide environment so the SYSTEM task (and all users) agree on config.
#    - bind all interfaces on 11434 (same port; preserves network reachability)
#    - point at the existing user model store (SYSTEM's default profile differs)
#    - preserve the current keep-alive behaviour (-1 = never unload). For marker
#      co-tenancy on this GPU later, change to e.g. '5m'.
[Environment]::SetEnvironmentVariable('OLLAMA_HOST',       '0.0.0.0:11434', 'Machine')
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS',     $ModelsDir,      'Machine')
[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '-1',            'Machine')
Write-Host "Set machine env: OLLAMA_HOST=0.0.0.0:11434, OLLAMA_MODELS, OLLAMA_KEEP_ALIVE=-1"

# 2. Stop the desktop app + any running serve so port 11434 is free.
Get-Process 'ollama app','ollama' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 3. Park the desktop auto-start shortcut so it does not reclaim 11434 on next login.
$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup 'Ollama.lnk'
if (Test-Path $lnk) {
  Move-Item $lnk "$lnk.disabled" -Force
  Write-Host "Parked startup shortcut: $lnk -> $lnk.disabled"
}

# 4. (Re)create the scheduled task: run `ollama serve` as SYSTEM, at boot, no time limit.
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action    = New-ScheduledTaskAction  -Execute $OllamaExe -Argument 'serve'
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "Registered scheduled task '$TaskName' (SYSTEM, AtStartup, no time limit)"

# 5. Start it now.
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 8

# 6. Verify: listening socket, API, and that the GPU is usable under SYSTEM.
$listen = (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).LocalAddress
Write-Host "Listening on 11434: $listen"
try {
  $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 8
  Write-Host ("Models served: " + (($tags.models.name) -join ', '))
} catch { Write-Host "WARN: /api/tags not responding yet: $($_.Exception.Message)" }
Write-Host "Done. Verify GPU use with a request, then 'ollama ps' should show processor=GPU."
