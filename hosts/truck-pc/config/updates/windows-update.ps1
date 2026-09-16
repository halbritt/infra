$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$output = 'C:\ProgramData\Infra\windows-update-result.json'
try {
    $session = New-Object -ComObject Microsoft.Update.Session
    $session.ClientApplicationID = 'Infra authorized maintenance'
    $result = $session.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Software' and IsHidden=0")
    $updates = New-Object -ComObject Microsoft.Update.UpdateColl
    foreach ($update in $result.Updates) {
        if (-not $update.EulaAccepted) { $update.AcceptEula() }
        [void]$updates.Add($update)
    }
    if ($updates.Count -eq 0) {
        @{Stage='Complete'; Updates=@(); RebootRequired=$false} | ConvertTo-Json | Set-Content $output
        exit 0
    }
    @{Stage='Downloading'; Titles=@($updates | ForEach-Object {$_.Title})} | ConvertTo-Json | Set-Content $output
    $downloader = $session.CreateUpdateDownloader()
    $downloader.Updates = $updates
    $download = $downloader.Download()
    if ($download.ResultCode -ne 2) { throw "Windows Update download result: $($download.ResultCode)" }
    @{Stage='Installing'; Titles=@($updates | ForEach-Object {$_.Title})} | ConvertTo-Json | Set-Content $output
    $installer = $session.CreateUpdateInstaller()
    $installer.Updates = $updates
    $installation = $installer.Install()
    $items = for ($i=0; $i -lt $updates.Count; $i++) {
        $item = $installation.GetUpdateResult($i)
        [pscustomobject]@{Title=$updates.Item($i).Title; ResultCode=[int]$item.ResultCode; HResult=$item.HResult}
    }
    @{Stage='Complete'; ResultCode=[int]$installation.ResultCode; RebootRequired=$installation.RebootRequired; Updates=@($items)} | ConvertTo-Json -Depth 4 | Set-Content $output
    if ($installation.ResultCode -ne 2) { exit 1 }
} catch {
    @{Stage='Failed'; Error=$_.Exception.Message} | ConvertTo-Json | Set-Content $output
    throw
}
