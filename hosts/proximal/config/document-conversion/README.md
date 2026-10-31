# Local document conversion

Marker and Docling run locally on Proximal. The owner requested a Marker update,
a working Surya backend, and installation of current Docling on 2026-10-31.
The old Marker venv followed `/usr/bin/python3` to Python 3.14 after the OS
upgrade and could no longer find its Python 3.12 packages.

## Installed state

| Component | Version / location |
|---|---|
| Marker | `marker-pdf[full]` 2.1.0, `~/git/marker/.venv` (Python 3.12) |
| Surya | `surya-ocr` 0.23.0, in Marker's venv |
| Surya weights | `datalab-to/surya-ocr-2.5-gguf`, HF revision `eb78671ae9af9bdddfac2e25507c55337b6098e2` |
| Inference | `~/git/llama.cpp/build/bin/llama-server`, auto-spawned on loopback |
| Docling | 2.145.0, uv tool environment `~/.local/share/uv/tools/docling` |
| Torch | 2.15.0+cpu in both environments |

The upstream Marker checkout was fast-forwarded to `71dd5fd`. Runtime packages
come from PyPI, independently of that checkout. Docling has its own environment:
its Pillow/OpenCV requirements differ from Surya's. Model downloads are cached
under `~/.cache/huggingface/hub`; OCR inference stays local.

The 3090 had only 958 MiB free during installation. Use CPU inference alongside
the resident LLM and speech services. The launcher hides CUDA, sets both Torch
and llama.cpp to CPU, disables projector offload, and gives Surya one 24,576-token
slot. `TORCH_DEVICE=cpu` alone does not configure Surya's separate inference
server. No resident service needs to stop.

## Install and update

Run `bash install.sh` from this directory. It installs the pinned packages with
CPU Torch and installs `run-marker.sh` as `~/.local/bin/marker-local`.
`uv` and the existing llama.cpp build are prerequisites. Change the package pins
in the installer when updating; rerun conversion checks before recording success.
Do not reuse an environment whose interpreter has changed underneath it.

| Canonical file | Installed path |
|---|---|
| `run-marker.sh` | `~/.local/bin/marker-local` |
| `install.sh` | Run from this repository; not copied |

```bash
# Marker, with Surya started automatically when OCR is needed
marker-local marker_single file.pdf --output_dir out --output_format markdown

# Direct Surya 2.5 OCR; also accepts PDFs and directories
marker-local surya_ocr scan.png --output_dir out
marker-local surya_layout file.pdf --output_dir layout
marker-local surya_table table.png --output_dir tables

# Current Docling uses the convert subcommand
docling convert file.pdf --device cpu --to md --to json --output out --fail-on partial
```

Marker defaults to fast mode on CPU. Use `--mode balanced` to exercise VLM layout
and OCR directly. Direct Surya output is `out/<stem>/results.json`; Marker output
is `out/<stem>/<stem>.md`; Docling writes `out/<stem>.md` and `.json`.
Upstream normally stops the Surya VLM at command exit. Do not use
`--keep_server` for an ordinary one-off conversion. The small fast-layout and
OCR-error CPU servers persist for reuse even without that flag (upstream shared
batch-service behavior). The servers started by these smoke checks were stopped
after verification; no permanent service was installed.

The skillpack `marker-convert` helper supports local conversion and an optional
Windows peecee bridge. That remote installation was not updated or verified by
this Proximal change. Maintain skill instructions in `~/git/skillpack`, then run
its `install.sh` to deploy them.

## Verification (2026-10-31)

- Both environments pass `uv pip check`; CLI help loads successfully.
- A locally generated image containing three text lines was read by Surya 2.5
  through CPU llama.cpp, producing the expected text and bounding boxes with
  no block errors.
- Docling converted the corresponding scanned PDF into Markdown and structured
  JSON with OCR enabled, recovering all three lines (about 30 seconds).
- Marker balanced-mode OCR produced the expected Markdown in about 28 seconds.
  The skillpack helper passed its default fast-mode scanned-PDF path and
  produced structured JSON with the expected OCR text (35 seconds including
  startup and shutdown).
- The resident `llama-27b` service stayed active; GPU free memory remained
  958 MiB. All 43 infrastructure tests and repository validation passed.

Smoke inputs, outputs and logs: `~/.cache/document-tools-update/`.
The unusable old venv is retained there as `marker-venv-before-20261031` for
inspection; it is not a runnable rollback environment.

Upstream references: [Marker](https://github.com/datalab-to/marker),
[Surya inference backends](https://github.com/datalab-to/surya#inference-backends),
[Docling installation](https://docling-project.github.io/docling/getting_started/installation/).
