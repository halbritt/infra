# install-kev.ps1
# Install Kev (jaredpalmer/kev: Qwen3.5-4B-Base + LoRA + pointer head, a System One
# compatible calibrated classifier) on peecee, into an isolated uv-managed venv, so the
# RTX 3090 Ti can serve it beside the resident ollama model (qwen3-vl:8b, ~8 GB).
# Run on peecee (no elevation needed; user-scope install). Idempotent.
#
# Pins (2026-09-23, measured working on proximal's CUDA 12.8 venv and resolved on
# native Windows): torch 2.8.0+cu128, flash-linear-attention 0.5.2 (the Qwen3.5
# Gated-DeltaNet kernels; the reference path is ~100x slower), triton-windows 3.4
# (fla's kernel compiler on Windows; no MSVC needed), kev at commit 557598f (installed from
# the GitHub source tarball: peecee has no git).

# Not 'Stop': under PowerShell 5.1 with stderr redirected, a native tool's first stderr line
# (uv prints progress there) becomes a terminating error. Exit codes are checked instead.
$ErrorActionPreference = 'Continue'
function Check($what) { if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $what (exit $LASTEXITCODE)"; exit 1 } }
$Root = Join-Path $env:USERPROFILE 'kev'
$Venv = Join-Path $Root '.venv'
$VPy  = Join-Path $Venv 'Scripts\python.exe'
$KevCommit = '557598fced1dada75dfbf36ed144dce309ac6ceb'

$uvExe = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uvExe) { $uvExe = Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
if (-not (Test-Path $uvExe)) { throw "uv not found (install-marker.ps1 installs it)" }

New-Item -ItemType Directory -Force -Path $Root, (Join-Path $Root 'hf'), (Join-Path $Root 'logs') | Out-Null
if (-not (Test-Path $VPy)) { & $uvExe venv $Venv --python 3.12; Check 'uv venv' } else { Write-Host "venv exists: $Venv" }
& $uvExe pip install --python $VPy --torch-backend=cu128 `
    'torch==2.8.0' 'triton-windows<3.5' 'flash-linear-attention==0.5.2' `
    "kev[serve] @ https://github.com/jaredpalmer/kev/archive/$KevCommit.tar.gz"
Check 'uv pip install'

& $VPy -c "import torch, fla, kev; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE')"
Check 'import check'
Write-Host "kev venv: $Venv"
Write-Host "weights download on first serve into $(Join-Path $Root 'hf') (HF_HOME); ~9 GB"
