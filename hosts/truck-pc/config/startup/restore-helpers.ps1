$ErrorActionPreference = 'Stop'
$state = Get-Content 'C:\ProgramData\Infra\startup-before-20260915.json' -Raw | ConvertFrom-Json
foreach ($entry in $state.RunEntries) {
    New-ItemProperty -Path $entry.Path -Name $entry.Name -Value $entry.Value -PropertyType $entry.Kind -Force | Out-Null
}
foreach ($task in $state.Tasks) {
    if ($task.Enabled) { Enable-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath | Out-Null }
}
foreach ($service in $state.Services) {
    if ($service.Name -eq 'CoworkVMService') { continue }
    Set-Service -Name $service.Name -StartupType $service.StartType
    if ($service.Status -eq 'Running') { Start-Service -Name $service.Name }
}
$coworkBackup = 'C:\ProgramData\Infra\cowork-start-before-20260915.json'
if (Test-Path $coworkBackup) {
    $cowork = Get-Content $coworkBackup -Raw | ConvertFrom-Json
    Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\CoworkVMService' -Name Start -Value $cowork.Start
    if ($cowork.WasRunning) { Start-Service CoworkVMService }
}
