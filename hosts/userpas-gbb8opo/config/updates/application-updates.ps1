param([switch]$Resume)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$output = 'C:\ProgramData\Infra\application-update-result.json'
$log = 'C:\ProgramData\Infra\application-update-log.txt'
$windowsTask = Get-ScheduledTask -TaskName 'InfraWindowsUpdates-20260915' -ErrorAction SilentlyContinue
if ($windowsTask -and $windowsTask.State -eq 'Running') { throw 'Wait for the Windows Update task before starting MSI application updates' }
$packages = @(
    'Adobe.CreativeCloud', 'calibre.calibre', 'Anthropic.Claude', 'Garmin.Express',
    'Microsoft.VCRedist.2013.x64', 'Microsoft.VCRedist.2013.x86',
    'Microsoft.VCRedist.2015+.x64', 'Microsoft.VCRedist.2015+.x86',
    'Microsoft.WindowsPCHealthCheck', 'Microsoft.WindowsAppRuntime.1.7', 'Microsoft.WindowsAppRuntime.1.8'
)
$results = @()
if ($Resume) {
    $previous = Get-Content $output -Raw | ConvertFrom-Json
    $results = @($previous.Results)
}
foreach ($id in $packages) {
    if (@($results | Where-Object {$_.Package -eq $id -and $_.ExitCode -eq 0}).Count) { continue }
    $results = @($results | Where-Object {$_.Package -ne $id})
    @{Stage='Upgrading'; Package=$id; Results=$results} | ConvertTo-Json -Depth 4 | Set-Content $output
    "Updating $id" | Out-File $log -Append -Encoding utf8
    $stdout = "C:\ProgramData\Infra\winget-$id.stdout.txt"
    $stderr = "C:\ProgramData\Infra\winget-$id.stderr.txt"
    $process = Start-Process -FilePath (Get-Command winget).Source -ArgumentList @('upgrade', '--id', $id, '--exact', '--source', 'winget', '--silent', '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity') -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Get-Content $stdout,$stderr | Out-File $log -Append -Encoding utf8
    $results += [pscustomobject]@{Package=$id; ExitCode=$process.ExitCode}
}
@{Stage='RestoringStartupPolicy'; Results=$results} | ConvertTo-Json -Depth 4 | Set-Content $output
& 'C:\ProgramData\Infra\manual-helpers.ps1'
& 'C:\ProgramData\Infra\manual-cowork.ps1'
@{Stage='Complete'; Results=$results} | ConvertTo-Json -Depth 4 | Set-Content $output
if (@($results | Where-Object {$_.ExitCode -ne 0}).Count -gt 0) { exit 1 }
