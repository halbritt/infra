$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$windowsTask = Get-ScheduledTask -TaskName 'InfraWindowsUpdates-20260915' -ErrorAction SilentlyContinue
if ($windowsTask -and $windowsTask.State -eq 'Running') { throw 'Wait for Windows Update to finish' }
$output = 'C:\ProgramData\Infra\application-update-result.json'
$previous = Get-Content $output -Raw | ConvertFrom-Json
$results = @($previous.Results | Where-Object {$_.Package -notlike 'Microsoft.WindowsAppRuntime.*'})
$runtimes = @(
    @{Id='Microsoft.WindowsAppRuntime.1.7'; Version='1.7.9'; Framework='7000.785.2325.0'; Url='https://aka.ms/windowsappsdk/1.7/1.7.260224002/windowsappruntimeinstall-x64.exe'; Hash='8DE73B13A010C6AEB84040E5587A46D21B36DECCE0CCD582C346536CAD63AE73'},
    @{Id='Microsoft.WindowsAppRuntime.1.8'; Version='1.8.10'; Framework='8000.921.1539.0'; Url='https://aka.ms/windowsappsdk/1.8/1.8.260710003/windowsappruntimeinstall-x64.exe'; Hash='B8CDA840267AB72797F654F801F9A064AB6D9E508CEDEE3DF79F772F104DB6D6'}
)
foreach ($runtime in $runtimes) {
    $id = $runtime.Id
    @{Stage='InstallingRuntime'; Package=$id; Results=$results} | ConvertTo-Json -Depth 5 | Set-Content $output
    $installer = "C:\ProgramData\Infra\$id-$($runtime.Version).exe"
    Invoke-WebRequest -UseBasicParsing -Uri $runtime.Url -OutFile $installer
    if ((Get-FileHash $installer -Algorithm SHA256).Hash -ne $runtime.Hash) { throw "Installer hash mismatch: $id" }
    $signature = Get-AuthenticodeSignature $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation,') { throw "Invalid Microsoft signature: $id" }
    $process = Start-Process $installer -ArgumentList '--quiet' -Wait -PassThru -RedirectStandardOutput "C:\ProgramData\Infra\$id.stdout.txt" -RedirectStandardError "C:\ProgramData\Infra\$id.stderr.txt"
    $result = [pscustomobject]@{Package=$id; Version=$runtime.Version; Method='Microsoft signed runtime installer'; ExitCode=$process.ExitCode; FrameworksVerified=$false}
    $results += $result
    @{Stage='VerifyingRuntime'; Package=$id; Results=$results} | ConvertTo-Json -Depth 5 | Set-Content $output
    if ($process.ExitCode -ne 0) { throw "Runtime installer failed: $id, exit $($process.ExitCode)" }
    $frameworks = @(Get-AppxPackage -Name $id | Where-Object {$_.Version -eq $runtime.Framework -and $_.Status -eq 'Ok'})
    foreach ($architecture in @('X86','X64')) {
        if (-not @($frameworks | Where-Object {[string]$_.Architecture -eq $architecture}).Count) { throw "Missing healthy $architecture framework $($runtime.Framework) for $id" }
    }
    $result.FrameworksVerified = $true
    @{Stage='RuntimeInstalled'; Package=$id; Results=$results} | ConvertTo-Json -Depth 5 | Set-Content $output
}
& 'C:\ProgramData\Infra\manual-helpers.ps1'
& 'C:\ProgramData\Infra\manual-cowork.ps1'
@{Stage='Complete'; Results=$results} | ConvertTo-Json -Depth 5 | Set-Content $output
if (@($results | Where-Object {$_.ExitCode -ne 0}).Count) { exit 1 }
