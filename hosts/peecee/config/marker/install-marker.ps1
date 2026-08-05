# install-marker.ps1
# Install marker-pdf on peecee with CUDA torch, into an isolated uv-managed venv, so
# peecee's RTX 3090 Ti can do batch GPU document conversion (PDF/office -> markdown/JSON).
# Run on peecee (no elevation needed; user-scope install). Idempotent.
#
# Uses uv + --torch-backend=auto, which detects the GPU/driver and installs the
# matching CUDA torch wheel (the Windows PyPI torch is CPU-only, so this matters).

$ErrorActionPreference = 'Stop'
$Root = Join-Path $env:USERPROFILE 'marker'
$Venv = Join-Path $Root '.venv'
$VPy  = Join-Path $Venv 'Scripts\python.exe'

# 1. uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "Installing uv..."
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}
$uvExe = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uvExe) { $uvExe = Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
if (-not (Test-Path $uvExe)) { throw "uv not found after install" }
Write-Host "uv: $uvExe"

# 2. isolated venv (Python 3.12, uv-fetched)
New-Item -ItemType Directory -Force -Path $Root | Out-Null
& $uvExe venv $Venv --python 3.12

# 3. marker-pdf + the CUDA torch build that matches this GPU (uv auto-selects)
& $uvExe pip install --python $VPy marker-pdf --torch-backend=auto

# 4. verify CUDA is actually wired to the 3090 Ti
& $VPy -c "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available()); print('gpu', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE')"
Write-Host "marker venv: $Venv"
Write-Host "marker_single: $(Join-Path $Venv 'Scripts\marker_single.exe')"
