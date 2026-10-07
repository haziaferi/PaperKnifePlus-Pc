# Line-art redaction on real PDFs (2026-10-07)

`realworld_check.py` over the PDFs that installed programs ship on the owner's machine
(`C:\Program Files`: Ghostscript examples and manuals, PDF24, ONLYOFFICE samples, the
browsers' sample PDF). Three boxes per page, seeded: two on drawn paths, one anywhere.
Each page is redacted with MuPDF alone (the app before L3-18) and with `redact_page`.

- *leak*: ink left inside a box (shrunk 3 px) with no fill, at 96 dpi;
- *shape left*: path vertices inside a box, or stroked outlines running through one;
- *damage*: ink changed by more than 48 levels outside the boxes (grown 3 px), with
  the black fill, after saving.

## Final code, seed 17: 104 pages from 73 files

| | MuPDF alone | `redact_page` |
|---|---|---|
| pages with ink left under a box | 83 (293 169 px) | 1 (12 px, see below) |
| pages with shape left in a box | 103 (10 861) | 0 |
| pages handled by the fallback | — | 0 |
| errors | 0 | 0 |
| pages with more damage than MuPDF alone | — | 3 (2, 5 and 152 px) |
| time, all pages | 31.1 s | 37.6 s (slowest page 9.9 s) |

The 12 px are the end cap of a 10 pt line cut at an angle on Ghostscript's
`text_graphic_image.pdf`: its corner reaches half a line width under the box. The
line is outside the box, and the fill covers it.

The extra damage is anti-aliasing. A table-cell clip with a corner inside a box is
cut, because the corner tells where the cell ends. MuPDF draws a rectangular clip with
pixel-exact edges but a cut one anti-aliased, so text sitting exactly on the cell's
edge renders a little lighter. The worst case is 152 px, along one line of an
ONLYOFFICE form.

## How it got here

Earlier runs on the same corpus found what the synthetic tests had not, and each
became a test case:

| found on | defect | fix |
|---|---|---|
| browsers' `confused_fox.pdf` (Figma) | shapes in a soft-mask group never cut (MuPDF's redaction skips them too), so the safety net fell back and removed the page's full-page backgrounds: about 300 000 px | `gs` → ExtGState `/SMask /G` is rewritten like a form |
| ONLYOFFICE samples | splitting a tiling-pattern fill re-tiles it: up to 2 000 px | fills whose vertices are all outside stay whole behind a clip |
| ONLYOFFICE samples | splitting a rectangle clip anti-aliases its edges | the same rule for clip paths |
| `confused_fox.pdf` | a Bézier control point just inside a box counted as hidden shape | only on-path points count |
| Ghostscript `GS9_Color_Management.pdf`, `proof_link.pdf` | form BBoxes (implicit clips) with a corner in a box | the private form copy gets a larger BBox and an explicit cut clip |
| `GS9_Color_Management.pdf` | an empty clip written at the form origin, which lay in the box | empty clips are placed far off the page |

A first sample from the owner's Downloads folder was stopped after 70 pages: it
reached personal documents. Its anonymised totals (old: ink left on 48 pages; new:
0) agreed with the above. Its logs, which named the files, were deleted.
