# uninstall-ollama-service.ps1
# Roll back install-ollama-service.ps1: remove the SYSTEM scheduled task and restore
# the Ollama desktop app. Run on peecee in an elevated shell.

$ErrorActionPreference = 'Continue'
$TaskName = 'OllamaServer'

# 1. Remove the scheduled task and stop the SYSTEM serve process.
schtasks /Delete /TN $TaskName /F *> $null
Get-Process 'ollama' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host "Removed task '$TaskName' and stopped serve."

# 2. Restore the desktop auto-start shortcut.
$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup 'Ollama.lnk'
if (Test-Path "$lnk.disabled") { Move-Item "$lnk.disabled" $lnk -Force; Write-Host "Restored $lnk" }

# 3. Relaunch the desktop app now (it re-binds 11434).
$app = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama app.exe'
if (Test-Path $app) { Start-Process $app; Write-Host "Relaunched desktop app." }

# 4. (Optional) clear the machine env we set — uncomment to fully revert:
# [Environment]::SetEnvironmentVariable('OLLAMA_HOST',$null,'Machine')
# [Environment]::SetEnvironmentVariable('OLLAMA_MODELS',$null,'Machine')
# [Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE',$null,'Machine')
Write-Host "Rollback complete."
