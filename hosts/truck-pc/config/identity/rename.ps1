$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$computer = Get-CimInstance Win32_ComputerSystem
if ($computer.Name -notin @('USERPAS-GBB8OPO', 'truck-pc') -or $computer.PartOfDomain) { throw 'Unexpected computer identity or domain membership' }
$sid = 'S-1-5-21-1644079127-1291031853-2162120719-1002'
$account = Get-LocalUser -SID $sid
if ($account.Name -notin @('User', 'halbritt')) { throw 'Unexpected account name for the recorded SID' }
$collision = Get-LocalUser | Where-Object {$_.Name -eq 'halbritt' -and [string]$_.SID -ne $sid}
if ($collision) { throw 'halbritt already belongs to another account' }
$tailscale = 'C:\Program Files\Tailscale\tailscale.exe'
if (-not (Test-Path $tailscale)) { throw 'Expected Tailscale installation is absent' }
$backup = 'C:\ProgramData\Infra\identity-before-20260915.json'
if (-not (Test-Path $backup)) {
    $profile = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$sid"
    $tailnet = & $tailscale status --json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read current Tailscale identity' }
    $tailnet = $tailnet | ConvertFrom-Json
    @{ComputerName=$computer.Name; UserName=$account.Name; FullName=$account.FullName; SID=$sid; ProfilePath=$profile.ProfileImagePath; TailnetDNSName=$tailnet.Self.DNSName} | ConvertTo-Json | Set-Content $backup -Encoding UTF8
}
$configuredName = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName').ComputerName
if ($configuredName -ne 'truck-pc') { Rename-Computer -NewName 'truck-pc' -Force }
& $tailscale set --hostname=truck-pc
if ($LASTEXITCODE -ne 0) { throw 'Tailscale hostname change failed' }
if ($account.Name -ne 'halbritt') { Rename-LocalUser -SID $sid -NewName 'halbritt' }
Set-LocalUser -Name 'halbritt' -FullName 'Heath Albritton'
Get-LocalUser -Name 'halbritt' | Select-Object Name,FullName,SID
'Verify SSH as halbritt, then restart to activate the Windows computer name.'
