# Omezizy D450 — changelog

## 2026-10-23 — print-label rewritten: host render + TSPL BITMAP

The owner asked for a USPS label PDF on peecee to be printed. The old `print-label`
failed twice:
- **Device detection** returned `/dev/usb/1-3.2` (the USB interface name) instead of
  `lp2`.
- **Rendering:** the snap CUPS's `cupsfilter`/gstoraster failed with
  `cfFilterGhostscript: Unexpected page count`, even on a re-saved PDF.

The new `print-label` (now tracked here) renders with host `pdftoppm` at 203 dpi,
thresholds to 1 bit (bit 0 = printed dot), scales to fit 812x1218 and sends
`SIZE 4,6 / GAP 0,0 / DIRECTION 1 / BITMAP / PRINT`. The label printed: the printer
answered `PRINTING:DOING`, and a preview reconstructed from the packed bits matched the
PDF. The old script is kept as `~/.local/bin/print-label.pre-bitmap-20261023`.

## 2026-08-29

- **Added device record.** Documented the D450 (QIN `2e3c:5756`, `MDL:D450`,
  TSPL `XPP,XL`, 203 dpi) USB-attached to `proximal`, including the intentional
  raw `OmezizyD450` CUPS queue and the two print paths: binkeeper's native-TSPL
  `bin_label.py` (bin labels) and `~/.local/bin/print-label` (arbitrary raster
  PDFs via the vendor `rastertolabeltspl` filter).
- **Recorded the print-failure diagnosis** (see `notes.md`): raw-queue + PDF
  mismatch, the 8-bit-"W" vs 1-bit-"K" raster trap, bit-0 bitmap polarity, and
  the snap-CUPS filter-install limitation.
