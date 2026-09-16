$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$uninstaller = 'C:\Program Files\Tablet\Wacom\32\Remove.exe'
if (-not (Test-Path $uninstaller)) { throw 'Wacom uninstaller is absent; inspect installed state before proceeding' }
$process = Start-Process $uninstaller -ArgumentList '/u', '/s' -Wait -PassThru
Write-Output "Wacom uninstaller exit code: $($process.ExitCode)"
if ($process.ExitCode -notin @(0, 2)) { throw 'Wacom uninstall did not report success' }
if ($process.ExitCode -eq 2) { Write-Output 'Wacom removal requires a restart to finish' }
Get-Service '*Wacom*','*WTablet*' -ErrorAction SilentlyContinue | Select-Object Name,Status,StartType
