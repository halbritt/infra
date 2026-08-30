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
- **Arbitrary raster PDFs** (e.g. a USPS shipping label) — `~/.local/bin/print-label
  <pdf>` renders via the vendor `rastertolabeltspl` filter and sends TSPL to the
  device. Driver + PPD live in `~/label-printer/driver/`. This path exists only
  because a raster PDF cannot be expressed as native TSPL drawing commands.

## Constraints / gotchas

- The snap-based CUPS **cannot host the vendor filter**: the snap filesystem is
  read-only, `run-cupsd` force-resets `ServerBin` on every start, and
  `libcupsimage.so.2` is not bundled. That is why `print-label` bypasses CUPS for
  the raster case rather than "fixing" the queue.
- Bitmap polarity is **bit 0 = printed dot** (TSC convention).
- Raster input to the vendor filter must be **8-bit grayscale "W"** (from
  `cupsfilter`), not 1-bit "K" (from `gs -sDEVICE=cups`) — the latter prints
  distorted/inverted output with line artifacts.

See [`notes.md`](notes.md) for the 2026-08-29 print-failure diagnosis and
[`CHANGELOG.md`](CHANGELOG.md) for history.
