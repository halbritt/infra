# Marker GPU document conversion on peecee

This subsystem holds the canonical PowerShell used to install and run Marker on
peecee's GPU:

- [`install-marker.ps1`](install-marker.ps1) creates an isolated Python 3.12
  environment under `C:\Users\halbr\marker\.venv`, installs `marker-pdf` with a
  CUDA-capable Torch selected by `uv`, and verifies CUDA visibility.
- [`convert.ps1`](convert.ps1) validates the source, optionally unloads resident
  Ollama models, runs `marker_single.exe`, and prints the resulting path.

The live conversion script is `C:\Users\halbr\marker\convert.ps1`; its SHA-256
matched the canonical file during the 2026-08-05 import. The installer is copied
there only when installation or refresh is required. The proximal-side
`marker-convert` skill invokes `marker/convert.ps1` over SSH and transfers input
and output separately. Documents, generated output, the virtual environment,
model caches, and SSH credentials do not belong in this repository.

## Install or refresh

From the infrastructure repository root:

```bash
ssh peecee 'powershell -NoProfile -Command "New-Item -ItemType Directory -Force marker | Out-Null"'
scp hosts/peecee/config/marker/install-marker.ps1 \
  hosts/peecee/config/marker/convert.ps1 peecee:marker/
```

Then run the installer from an elevated PowerShell session on peecee:

```powershell
.\marker\install-marker.ps1
```

The installer changes Python packages and may download large model or Torch
artifacts. Do not run it as a documentation check.

## Conversion behavior

```powershell
.\marker\convert.ps1 -Source marker-in\document.pdf -Format markdown -Out marker\out
```

Use `-KeepOllama` only when enough VRAM is independently established. Without
that switch, the runner asks Ollama to unload each currently listed model before
starting Marker. It does not restore the prior model; later inference reloads a
model through the normal fleet path.
