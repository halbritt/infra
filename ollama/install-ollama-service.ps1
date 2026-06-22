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
[Environment]::SetEnvironmentVariable('OLLAMA_HOST',         '0.0.0.0:11434', 'Machine')
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS',       $ModelsDir,      'Machine')
[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE',   '-1',            'Machine')
# q8_0 KV-cache quant halves KV memory so a Q4-class 27B stays fully resident on the
# 24 GiB card at a long context (no CPU spill). It silently no-ops without flash attn.
[Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE',  'q8_0', 'Machine')
[Environment]::SetEnvironmentVariable('OLLAMA_FLASH_ATTENTION','1',    'Machine')
Write-Host "Set machine env: OLLAMA_HOST, OLLAMA_MODELS, OLLAMA_KEEP_ALIVE=-1, OLLAMA_KV_CACHE_TYPE=q8_0, OLLAMA_FLASH_ATTENTION=1"

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

# 4. (Re)create the scheduled task. The SYSTEM service has no console, and a bare
#    `ollama serve` writes no logfile, so wrap it in a cmd that redirects stdout+stderr
#    to a logfile -- this is what makes the startup "server config" line and the
#    per-load KV-cache line auditable (e.g. confirming type_k=q8_0, not f16).
$LogDir = 'C:\ProgramData\Ollama'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Wrapper = Join-Path $LogDir 'run-ollama-serve.cmd'
@"
@echo off
"$OllamaExe" serve >> "$LogDir\server.log" 2>&1
"@ | Set-Content -Path $Wrapper -Encoding ASCII

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action    = New-ScheduledTaskAction  -Execute 'cmd.exe' -Argument "/c `"$Wrapper`""
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "Registered scheduled task '$TaskName' (SYSTEM, AtStartup, logs -> $LogDir\server.log)"

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
