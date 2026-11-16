# install-whisper.ps1
# Install whisper.cpp's prebuilt CUDA whisper-server and the large-v3-turbo GGML model
# under C:\Users\halbr\whisper. Idempotent: verifies SHA-256 and skips what is present.
# Checks exit codes instead of $ErrorActionPreference = 'Stop' (native stderr under
# PowerShell 5.1 would otherwise abort; see ../kev/README.md gotchas).
$Root    = Join-Path $env:USERPROFILE 'whisper'
$Build   = 'b5454'   # ggml-org/whisper.cpp CI build published with v1.9.5 (2026-10-06)
$ZipName = 'whisper-bin-win-cuda-12.4.0-x64.zip'
$ZipUrl  = "https://github.com/ggml-org/whisper.cpp/releases/download/$Build/$ZipName"
$ZipSha  = 'afef0b881c500958921c3f5523b50e59ee2ec9b6f5cbd25b324c51ed308a957a'
$Model   = 'ggml-large-v3-turbo.bin'
$ModelUrl = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$Model"
$ModelSha = '1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69'

function Fetch($url, $dest, $sha) {
    if ((Test-Path $dest) -and ((Get-FileHash $dest -Algorithm SHA256).Hash -ieq $sha)) {
        Write-Host "ok (cached): $dest"; return
    }
    Write-Host "downloading $url"
    & curl.exe -fL --retry 3 -sS -o $dest $url
    if ($LASTEXITCODE -ne 0) { throw "download failed ($LASTEXITCODE): $url" }
    $got = (Get-FileHash $dest -Algorithm SHA256).Hash
    if ($got -ine $sha) { throw "sha256 mismatch for ${dest}: got $got, want $sha" }
    Write-Host "ok: $dest"
}

New-Item -ItemType Directory -Force -Path $Root, "$Root\models", "$Root\logs", "$Root\dl" | Out-Null
Fetch $ZipUrl   "$Root\dl\$ZipName"  $ZipSha
Fetch $ModelUrl "$Root\models\$Model" $ModelSha

$Bin = "$Root\bin"
if (Test-Path $Bin) { Remove-Item -Recurse -Force $Bin }
Expand-Archive -Path "$Root\dl\$ZipName" -DestinationPath $Bin -Force
$Server = Get-ChildItem -Recurse -Path $Bin -Filter 'whisper-server.exe' | Select-Object -First 1
if (-not $Server) { throw "whisper-server.exe not found in $ZipName" }
Set-Content -Path "$Root\server-path.txt" -Value $Server.FullName -Encoding ascii
Write-Host "server: $($Server.FullName)"
