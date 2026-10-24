# Omezizy D450 label printer (proximal)

Durable, cross-agent provenance for the 4x6 direct-thermal label printer
USB-attached to `proximal`. It is a QIN `2e3c:5756` "QIN LabelPrinter" rebranded
as **Omezizy D450**; its IEEE-1284 ID reports `MDL:D450`, command set
`XPP,XL` (a TSPL dialect, *not* ZPL), 203 dpi.

## Identity

| fact | value |
|---|---|
| Resource name | `omezizy-d450` |
| USB | `2e3c:5756` (QIN), printer-class, bidirectional |
| IEEE-1284 | `MFG: ;CMD:XPP,XL;MDL:D450;CLS:PRINTER;DES:D450;` |
| Device node | `/dev/usb/lp2` (usblp; number varies — auto-detect by `MDL:D450`) |
| Command set | TSPL (`XPP,XL`) |
| Media | 4x6 direct-thermal label, 203 dpi (8 dots/mm) |
| CUPS queue | `OmezizyD450` — **raw**, `usb:///D450?serial=Q356E5BJ6710015` |

## How it is driven

The D450 speaks TSPL natively, so labels are emitted as TSPL drawing commands
(`SIZE`/`GAP`/`CLS`/`TEXT`/`QRCODE`/`BAR`/`PRINT`) and written straight to the
device — no raster, no driver, no CUPS filter.

- **Bin labels** — `~/git/binkeeper/src/binkeeper/bin_label.py`
  (`render_tspl` + `send_to_printer`) is the canonical, tested path (verified
  2026-06-25). It writes TSPL to `/dev/usb/lp*` or spools through the raw queue
  (`lp -d OmezizyD450 -o raw`). **The raw queue is intentional — leave it raw.**
- **Arbitrary PDFs** (e.g. a USPS shipping label) — `print-label FILE.pdf [COPIES]`
  ([source](print-label), installed at `~/.local/bin/print-label`). It renders page 1 at
  203 dpi with the host's `pdftoppm` and sends it as a TSPL `BITMAP` straight to the
  device, with no CUPS and no vendor filter. Since 2026-10-23 it no longer uses the vendor
  `rastertolabeltspl` filter (still in `~/label-printer/driver/`), because the snap CUPS's
  Ghostscript now fails.
- **From the Windows PC (peecee):** there is no Windows driver. Copy the PDF to proximal
  and run `print-label` (an agent can read it from `/mnt/c/Users/halbr/Downloads` via
  peecee-wsl).

## Constraints / gotchas

- The snap-based CUPS **cannot host the vendor filter**: the snap filesystem is
  read-only, `run-cupsd` force-resets `ServerBin` on every start, and
  `libcupsimage.so.2` is not bundled. Its `cupsfilter` also cannot read files in hidden
  directories under `$HOME`, and as of 2026-10-23 its Ghostscript fails on PDFs
  (`cfFilterGhostscript: Unexpected page count`). `print-label` avoids CUPS entirely.
- Bitmap polarity is **bit 0 = printed dot** (TSC convention).
- Raster input to the vendor filter must be **8-bit grayscale "W"** (from
  `cupsfilter`), not 1-bit "K" (from `gs -sDEVICE=cups`) — the latter prints
  distorted/inverted output with line artifacts.

See [`notes.md`](notes.md) for the 2026-08-29 print-failure diagnosis and
[`CHANGELOG.md`](CHANGELOG.md) for history.
