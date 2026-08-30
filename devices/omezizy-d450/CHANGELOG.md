# Omezizy D450 — changelog

## 2026-08-29

- **Added device record.** Documented the D450 (QIN `2e3c:5756`, `MDL:D450`,
  TSPL `XPP,XL`, 203 dpi) USB-attached to `proximal`, including the intentional
  raw `OmezizyD450` CUPS queue and the two print paths: binkeeper's native-TSPL
  `bin_label.py` (bin labels) and `~/.local/bin/print-label` (arbitrary raster
  PDFs via the vendor `rastertolabeltspl` filter).
- **Recorded the print-failure diagnosis** (see `notes.md`): raw-queue + PDF
  mismatch, the 8-bit-"W" vs 1-bit-"K" raster trap, bit-0 bitmap polarity, and
  the snap-CUPS filter-install limitation.
