$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$backup = 'C:\ProgramData\Infra\startup-before-20260915.json'
New-Item -ItemType Directory -Path (Split-Path $backup) -Force | Out-Null
$serviceNames = @('SupportAssistAgent', 'DellTechHub', 'DellClientManagementService', 'SamsungMagicianSVC', 'CMigrationService', 'EpsonScanSvc')
$services = @(Get-Service -Name $serviceNames)
$tasks = @(Get-ScheduledTask -TaskName 'Dell SupportAssistAgent AutoUpdate', 'SamsungMagician')
$runEntries = @()
$runPaths = @('HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run')
$runPaths += @(Get-ChildItem Registry::HKEY_USERS | Where-Object {$_.PSChildName -match '^S-1-5-21-.*-\d+$'} | ForEach-Object { 'Registry::' + $_.Name + '\SOFTWARE\Microsoft\Windows\CurrentVersion\Run' })
foreach ($path in $runPaths) {
    if (-not (Test-Path $path)) { continue }
    $key = Get-Item $path
    foreach ($name in @('Adobe CCXProcess', 'Adobe Creative Cloud', 'GarminExpress', 'Spotify', 'RobloxPlayerBeta')) {
        if ($key.GetValueNames() -contains $name) {
            $runEntries += [pscustomobject]@{Path=$path; Name=$name; Value=$key.GetValue($name); Kind=[string]$key.GetValueKind($name)}
        }
    }
}
if (-not (Test-Path $backup)) { [pscustomobject]@{
    Services=@($services | Select-Object Name,@{n='StartType';e={[string]$_.StartType}},@{n='Status';e={[string]$_.Status}})
    Tasks=@($tasks | Select-Object TaskName,TaskPath,@{n='Enabled';e={$_.Settings.Enabled}})
    RunEntries=$runEntries
} | ConvertTo-Json -Depth 6 | Set-Content $backup -Encoding UTF8 }
foreach ($service in $services) {
    Set-Service -Name $service.Name -StartupType Manual
    if ($service.Status -eq 'Running') {
        if ($service.CanStop) { Stop-Service -Name $service.Name }
        else { Write-Warning "$($service.Name) does not accept stop requests; manual startup takes effect after restart" }
    }
    Write-Output "Manual: $($service.Name)"
}
foreach ($task in $tasks) {
    Disable-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath | Out-Null
    Write-Output "Disabled task: $($task.TaskName)"
}
foreach ($entry in $runEntries) {
    Remove-ItemProperty -Path $entry.Path -Name $entry.Name
    Write-Output "Removed login launch: $($entry.Name)"
}
$helperNames = @('SamsungMagician', 'Creative Cloud', 'Creative Cloud Helper', 'Creative Cloud UI Helper', 'CCXProcess', 'AdobeNotificationClient', 'Adobe Desktop Service', 'Dell.CoreServices.Client', 'Dell.TechHub.*', 'Dell.Update.SubAgent')
Get-Process -Name $helperNames -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Output "Rollback snapshot: $backup"
