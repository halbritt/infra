# Omezizy D450 — operational notes

## 2026-08-29 — print-failure diagnosis (PDF → D450)

A request to print `/tmp/Quinn.pdf` (a USPS shipping label) to the D450 failed
repeatedly. Findings, in order of discovery:

1. **The `OmezizyD450` CUPS queue is a raw queue** (by design — binkeeper spools
   native TSPL through it). Sending a PDF to a raw queue ships raw PDF bytes to
   the thermal printer, which reads each line as a command and returns
   `Cmd error:` for every line. This is why a naive `lp -d OmezizyD450 <pdf>`
   cannot work.

2. **The D450 speaks TSPL**, confirmed by its IEEE-1284 `CMD:XPP,XL` and by
   binkeeper's already-working `bin_label.py`, which emits native TSPL
   (`SIZE`/`GAP`/`CLS`/`TEXT`/`QRCODE`/`BAR`/`PRINT`) to `/dev/usb/lp*`. Bin
   labels therefore need no raster pipeline at all.

3. For an **arbitrary raster PDF** (not drawable as native TSPL), the path is
   PDF → 8-bit grayscale CUPS raster → vendor `rastertolabeltspl` filter → TSPL
   bitmap → `/dev/usb/lp*`. Two traps:
   - The raster must be **8-bit color-space "W"** (grayscale). Feeding a 1-bit
     "K" raster (e.g. `gs -sDEVICE=cups`) inverts and mis-packs the bitmap →
     "distorted label with a bunch of lines".
   - Bitmap polarity is **bit 0 = printed dot** (TSC convention). Verified by
     reconstructing the TSPL bitmap and diffing against the source PDF (88.6%
     pixel agreement at bit-0, 11.4% at bit-1).

4. **The vendor filter cannot be installed into the snap CUPS.** `run-cupsd`
   force-resets `ServerBin` to the read-only `$SNAP/lib/cups` on every start;
   the snap filesystem is read-only (no new bind-mount targets); and
   `libcupsimage.so.2` is not bundled. A `ServerBin` override in
   `cups-files.conf` is clobbered on restart. The only route would be a
   destructive bind-mount over an existing snap filter plus a persistence unit,
   and it breaks on every `snap refresh cups`. Rejected.

Result: the raw queue stays raw (binkeeper's contract); the one-off raster-PDF
case is handled by the standalone `~/.local/bin/print-label` script (driver +
`libcupsimage.so.2` at `~/label-printer/driver/`), which renders via
`snap run cups.cupsfilter` and writes TSPL straight to the device.
