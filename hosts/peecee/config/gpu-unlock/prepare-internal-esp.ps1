# One-time peecee storage preparation. Default is inspection; -Apply executes.
# Never formats an existing partition. Stop and inspect the receipt after failure.
param([switch]$Apply)
$ErrorActionPreference='Stop'
$esp='{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'
$before=@(Get-Partition -DiskNumber 0 | Select-Object DiskNumber,PartitionNumber,Guid,Offset,Size,GptType,IsSystem,IsBoot)
$disk=Get-Disk -Number 0
$c=Get-Partition -DriveLetter C
$win=Get-Partition -DiskNumber 0 -PartitionNumber 1
$recovery=Get-Partition -DiskNumber 0 -PartitionNumber 3
if($disk.UniqueId -ne 'eui.002538414143DCE7' -or $disk.FriendlyName -ne 'Samsung SSD 990 PRO 4TB' -or $disk.PartitionStyle -ne 'GPT' -or $disk.HealthStatus -ne 'Healthy' -or $disk.IsOffline -or $disk.IsReadOnly){throw 'Unexpected system disk'}
if($before.Count -ne 3 -or $c.DiskNumber -ne 0 -or $c.Guid -ne '{80d78185-e526-4157-ac38-0b058085c66d}' -or $c.Size -ne 3999679716352 -or $c.Offset -ne 105906176){throw 'C: geometry changed; this is not a repeatable apply operation'}
if($win.Guid -ne '{c4b263fb-2821-4034-a2b0-3f3a4dfacc15}' -or !$win.IsSystem -or $win.Size -ne 104857600 -or $win.Offset -ne 1048576 -or $win.GptType -ne $esp){throw 'Windows ESP changed'}
if($recovery.Guid -ne '{6b435d17-6163-4a67-b1e8-370cd6c69d22}' -or $recovery.Offset -ne 3999785811968 -or $recovery.Size -ne 999292928){throw 'Recovery partition changed'}
if(@(Get-Volume | Where-Object DriveLetter -eq 'U').Count -or (Test-Path 'U:\')){throw 'U: already in use'}
$enc=Get-BitLockerVolume -MountPoint C:
if([int]$enc.VolumeStatus -ne 0 -or [int]$enc.ProtectionStatus -ne 0){throw 'C: must be fully decrypted'}
$cv=$c | Get-Volume
if($cv.FileSystem -ne 'NTFS' -or $cv.HealthStatus -ne 'Healthy' -or $cv.SizeRemaining -lt 10GB){throw 'C: volume is unsuitable'}
$offset=[uint64]([math]::Floor(($c.Offset+$c.Size-1GB)/1MB)*1MB)
$newSize=[uint64]($offset-$c.Offset)
if((Get-PartitionSupportedSize -DriveLetter C).SizeMin -gt $newSize){throw 'Native NTFS shrink cannot provide 1 GiB'}
$loader=Join-Path ($win | Get-Volume).Path 'EFI\Microsoft\Boot\bootmgfw.efi'
$loaderHash=(Get-FileHash -LiteralPath $loader).Hash
$fw=@(& bcdedit /enum firmware);if($LASTEXITCODE){throw 'Cannot read firmware'}
if(($fw -join "`n") -match '(?mi)^bootsequence\s+'){throw 'Pending boot sequence'}
$plan=[ordered]@{DiskUniqueId=$disk.UniqueId;Before=$before;NewCSize=$newSize;NewEspOffset=$offset;NewEspSize=1GB;WindowsLoaderSha256=$loaderHash;Phase='planned'}
if(!$Apply){$plan | ConvertTo-Json -Depth 6;return}
$backup=Join-Path $env:ProgramData ('WindowsGPUUnlock\StorageBackups\'+(Get-Date -Format 'yyyyMMdd-HHmmssfff'))
[void][IO.Directory]::CreateDirectory($backup)
function Save { $plan | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $backup 'receipt.json') }
Save
& bcdedit /export (Join-Path $backup 'BCD-export');if($LASTEXITCODE){throw 'BCD backup failed'}
$fw | Set-Content -LiteralPath (Join-Path $backup 'firmware-before.txt')
Copy-Item -LiteralPath $loader -Destination (Join-Path $backup 'bootmgfw.efi')
if((Get-FileHash (Join-Path $backup 'bootmgfw.efi')).Hash -ne $loaderHash){throw 'Loader backup mismatch'}
try {
 $plan.Phase='shrinking';Save
 Resize-Partition -DriveLetter C -Size $newSize
 $shrunk=Get-Partition -DriveLetter C
 if($shrunk.Guid -ne $c.Guid -or $shrunk.Size -ne $newSize -or $shrunk.Offset -ne $c.Offset){throw 'Shrink readback mismatch'}
 $plan.Phase='creating';Save
 $new=New-Partition -DiskNumber 0 -Offset $offset -Size 1GB -GptType $esp -DriveLetter U
 $plan.NewPartitionGuid=$new.Guid;$plan.NewPartitionNumber=$new.PartitionNumber;Save
 $new=Get-Partition -DriveLetter U
 if($new.Guid -ne $plan.NewPartitionGuid -or $new.Guid -in $before.Guid -or $new.DiskNumber -ne 0 -or $new.Offset -ne $offset -or $new.Size -ne 1GB -or $new.GptType -ne $esp -or $new.IsBoot -or $new.IsSystem){throw 'New partition identity mismatch; refusing format'}
 $nv=$new | Get-Volume
 if($nv.FileSystem -and $nv.FileSystem -ne 'RAW'){throw 'New partition already contains a filesystem; refusing format'}
 $plan.Phase='formatting-new-partition';Save
 $new | Format-Volume -FileSystem FAT32 -NewFileSystemLabel GPUUNLOCK -Confirm:$false | Out-Null
 if((Get-Volume -DriveLetter U).FileSystem -ne 'FAT32'){throw 'Format readback mismatch'}
 foreach($old in $before | Where-Object {$_.Guid -ne $c.Guid}){
  $now=Get-Partition -DiskNumber 0 -PartitionNumber $old.PartitionNumber
  if($now.Guid -ne $old.Guid -or $now.Offset -ne $old.Offset -or $now.Size -ne $old.Size -or $now.GptType -ne $old.GptType){throw 'Existing partition changed'}
 }
 if((Get-FileHash -LiteralPath $loader).Hash -ne $loaderHash){throw 'Windows loader changed'}
 $afterFw=@(& bcdedit /enum firmware);if($LASTEXITCODE -or ($afterFw -join "`n") -cne ($fw -join "`n")){throw 'Firmware entries changed'}
 $plan.After=@(Get-Partition -DiskNumber 0 | Select-Object DiskNumber,PartitionNumber,Guid,Offset,Size,GptType,IsSystem,IsBoot)
 $plan.Phase='verified';Save
 Write-Output "Created and verified dedicated 1 GiB ESP U:. Receipt: $backup"
} catch {$plan.Error=$_.Exception.Message;Save;throw}
