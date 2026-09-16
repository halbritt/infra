$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$backup = 'C:\ProgramData\Infra\power-before-20260916.json'
if (-not (Test-Path $backup)) {
    $schemeOutput = powercfg /getactivescheme
    $sleepOutput = powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
    $hibOutput = powercfg /q SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE
    @{
        Scheme = ($schemeOutput -join "`n");
        Standby = ($sleepOutput -join "`n");
        Hibernate = ($hibOutput -join "`n");
        Timestamp = (Get-Date).ToString('o')
    } | ConvertTo-Json | Set-Content $backup -Encoding UTF8
}

powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

Write-Output "Power configuration updated: Sleep on AC disabled."
powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
