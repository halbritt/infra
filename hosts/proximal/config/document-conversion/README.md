# Local document conversion

Marker, Docling and MinerU run locally on Proximal. The owner requested a Marker update,
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
| MinerU | 4.1.3, isolated uv tool `~/.local/share/uv/tools/mineru` (Python 3.12) |
| MinerU models | `MinerU-4_models_onnx` and `MinerU2.5-Pro-2605-1.2B-GGUF`, under `~/.mineru/models` |

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
CPU Torch for Marker/Docling and installs `run-marker.sh` as
`~/.local/bin/marker-local`. MinerU uses its own ONNX/llama.cpp environment. The
installer installs `mineru-config.yaml`, downloads/verifies Standard-tier assets
(including Basic), and disables telemetry through the native library service.
It enables the library's managed local parser and temporarily starts/stops the
library service when none was running; an existing service is left running.
`uv` and the existing llama.cpp build are prerequisites. Change the package pins
in the installer when updating; rerun conversion checks before recording success.
Do not reuse an environment whose interpreter has changed underneath it.

| Canonical file | Installed path |
|---|---|
| `run-marker.sh` | `~/.local/bin/marker-local` |
| `mineru-config.yaml` | `~/.mineru/config.yaml` |
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

# MinerU stateless local parsing; output parent must exist
mkdir -p out
mineru-kit parse file.pdf --tier basic -o out/mineru-basic.md
mineru-kit parse file.pdf --tier standard -o out/mineru-standard.md
```

Marker defaults to fast mode on CPU. Use `--mode balanced` to exercise VLM layout
and OCR directly. Direct Surya output is `out/<stem>/results.json`; Marker output
is `out/<stem>/<stem>.md`; Docling writes `out/<stem>.md` and `.json`.
Upstream normally stops the Surya VLM at command exit. Do not use
`--keep_server` for an ordinary one-off conversion. The small fast-layout and
OCR-error CPU servers persist for reuse even without that flag (upstream shared
batch-service behavior). The servers started by these smoke checks were stopped
after verification; no permanent service was installed.

The skillpack `document-convert` skill covers Marker, Surya, Docling and MinerU.
The older `marker` and `marker-convert` skill names point there; the existing
`marker-convert/scripts/` helper paths remain stable. The Windows peecee Marker
bridge was not updated or verified by this Proximal change. Infra also records a
separate CUDA Docling installation on peecee-wsl under the peecee WSL subsystem;
check its host notes and GPU lease requirements before use. Maintain skill
instructions in `~/git/skillpack`, then run its `install.sh` to deploy them.

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

## MinerU inventory — 2026-10-31

The owner recalled a possible MinerU installation and requested verification
before consolidating the document-conversion skills. Neither `mineru` nor the
older `magic-pdf` command was on PATH. No MinerU package was found in 35 checked
Python package locations across project venvs, worktrees, user uv tools, other
user venvs and standard site-package roots. Bounded source/tool directory scans,
Docker container/image listings, and system/user unit listings found no MinerU
installation. `~/git/marker/benchmarks/competitors/mineru_infer.sh` is an upstream
comparison script, not an installed runtime.

This initial inventory was local, not a check of every remote host or archive.
It preceded the authorized installation below; it is retained as provenance.


## MinerU installation and verification — 2026-10-31

The owner subsequently explicitly requested installation. Installed MinerU
4.1.3 using `uv tool install --python 3.12 mineru==4.1.3` with its base dependencies
(116 compatible packages), including ONNX Runtime 1.31.1 and mineru-llama-cpp
0.2.0. The approximately 2 GiB of downloaded model assets provide Basic and
Standard tiers. No Torch/VLM GPU environment was added.

`mineru-config.yaml` selects local cached assets, ONNX small models on CPU, and
the bundled llama.cpp VLM engine. In this version llama.cpp follows the ONNX CPU
device selection. Basic performs OCR, formulas and tables without the VLM;
Standard uses the additional 1.2B VLM. The general chat server and Surya weights
are independent of this model stack.

Verified Basic and Standard parsing of the generated scanned PDF. Both exported
all three expected text lines; logs showed ONNX `CPUExecutionProvider` and
Standard's `llama.cpp device policy: cpu`. `models verify --tier standard` passed
for both bundles. Basic also exported valid full-document `middle_json` with
one page and the expected text, and the library CLI passed a complete export
after enabling its managed parser and waiting for readiness. The resident LLM
stayed active, with GPU free memory unchanged
at 958 MiB. Logs and outputs are in `~/.cache/document-conversion-skill/`.

The optional library CLI (`mineru parse`) requires `mineru server start`; the
stateless `mineru-kit parse` command works without that daemon. The installer
sets `parse_server.local.mode=managed` through `mineru config set`; the upstream
default is disabled even when models are installed. After startup, inspect
`mineru server status --json` and wait for `parse_server.local.healthy=true`
before submitting a library parse. The library and parser are loopback/local.
Telemetry was persistently disabled using the native command and verified as
`disabled`, source `user`, after restart. No standing systemd service was
installed. Start the library explicitly for a session and stop it when finished. Start
it with `(cd ~/.mineru && mineru server start)`: the managed parser's empty
upload-directory default currently resolves to its working directory and
creates `blobs/` and `.mineru-service.lock` there. The installer starts it from
`~/.mineru` to keep runtime files outside source checkouts.
