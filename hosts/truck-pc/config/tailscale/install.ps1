$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$installer = Join-Path $env:TEMP 'tailscale-setup-1.102.4-amd64.msi'
Invoke-WebRequest -UseBasicParsing -Uri 'https://pkgs.tailscale.com/stable/tailscale-setup-1.102.4-amd64.msi' -OutFile $installer
$signature = Get-AuthenticodeSignature $installer
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Tailscale Inc\.') {
    throw "Unexpected installer signature: $($signature.Status) / $($signature.SignerCertificate.Subject)"
}
Write-Output "Verified signer: $($signature.SignerCertificate.Subject)"
Get-FileHash $installer -Algorithm SHA256 | Select-Object Algorithm, Hash
$process = Start-Process msiexec.exe -ArgumentList @('/i', "`"$installer`"", '/qn', '/norestart', 'TS_UNATTENDEDMODE=always') -Wait -PassThru
if ($process.ExitCode -notin @(0, 3010)) {
    throw "Tailscale installation failed with MSI exit code $($process.ExitCode)"
}
Write-Output "MSI exit code: $($process.ExitCode)"
& 'C:\Program Files\Tailscale\tailscale.exe' version
Get-Service Tailscale | Select-Object Name, Status, StartType
