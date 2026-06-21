# convert.ps1 — run marker on peecee's RTX 3090 Ti (batch GPU document conversion).
# Frees VRAM from ollama first (unloads loaded models) so surya fits, then converts.
# Usage:
#   convert.ps1 -Source <path> [-Format markdown|json|html|chunks] [-Out <dir>] [-KeepOllama]
param(
  [Parameter(Mandatory=$true)][string]$Source,
  [string]$Format = 'markdown',
  [string]$Out = (Join-Path $env:USERPROFILE 'marker\out'),
  [switch]$KeepOllama
)
$ErrorActionPreference = 'Stop'
$Venv = Join-Path $env:USERPROFILE 'marker\.venv'
$MarkerSingle = Join-Path $Venv 'Scripts\marker_single.exe'
if (-not (Test-Path $MarkerSingle)) { throw "marker not installed: $MarkerSingle (run install-marker.ps1)" }
if (-not (Test-Path $Source)) { throw "no such file: $Source" }

# Free the GPU: unload any resident ollama model so surya has VRAM headroom.
# (ollama reloads on its next LLM request — interactive use on proximal is unaffected.)
if (-not $KeepOllama) {
  try {
    $loaded = (& ollama ps) | Select-Object -Skip 1 |
              ForEach-Object { ($_ -split '\s{2,}')[0].Trim() } | Where-Object { $_ }
    foreach ($m in $loaded) { Write-Host "freeing GPU: ollama stop $m"; & ollama stop $m 2>$null }
    if ($loaded) { Start-Sleep -Seconds 2 }
  } catch { Write-Host "WARN: could not unload ollama: $($_.Exception.Message)" }
}

New-Item -ItemType Directory -Force -Path $Out | Out-Null
Write-Host "marker: converting '$Source' -> $Format on GPU ..."
$sw = [Diagnostics.Stopwatch]::StartNew()
& $MarkerSingle $Source --output_format $Format --output_dir $Out
$sw.Stop()

$stem = [IO.Path]::GetFileNameWithoutExtension($Source)
$ext  = switch ($Format) { 'json' { 'json' } 'chunks' { 'json' } 'html' { 'html' } default { 'md' } }
$result = Join-Path $Out "$stem\$stem.$ext"
Write-Host ("done in {0}s" -f [math]::Round($sw.Elapsed.TotalSeconds,1))
Write-Host "OUTPUT: $result"
