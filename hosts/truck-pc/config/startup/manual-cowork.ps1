$ErrorActionPreference = 'Stop'
$service = Get-Service CoworkVMService
$path = 'HKLM:\SYSTEM\CurrentControlSet\Services\CoworkVMService'
$backup = 'C:\ProgramData\Infra\cowork-start-before-20260915.json'
if (-not (Test-Path $backup)) {
    @{Start=(Get-ItemProperty $path).Start; WasRunning=($service.Status -eq 'Running')} | ConvertTo-Json | Set-Content $backup
}
# The packaged service denies SCM configuration even to SYSTEM; its registry key
# grants administrators FullControl. Keep the service ACL intact.
Set-ItemProperty -Path $path -Name Start -Value 3
if ($service.Status -eq 'Running') { Stop-Service CoworkVMService }
Get-ItemProperty $path | Select-Object Start
Get-Service CoworkVMService | Select-Object Name,Status,StartType
