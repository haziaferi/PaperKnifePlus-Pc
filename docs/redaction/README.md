# Redacting line art — options, evidence, scores (2026-10-02)

Register item **L3-18**: vector paths only partly under a redaction box survive.
This folder holds the evidence for choosing what Redact should do instead.

## What the app does today

`redact.py` calls `apply_redactions(images=PDF_REDACT_IMAGE_PIXELS)`, so line art uses
PyMuPDF's default `PDF_REDACT_LINE_ART_REMOVE_IF_COVERED`. MuPDF decides per subpath by
its bounding box and keeps or deletes it whole; it never cuts a path at the box edge
(`redaction-research.md`, MuPDF `pdf-clean.c` / `pdf-op-filter.c`). So a signature,
chart line or underline that crosses the box edge stays complete underneath it, and
the bench below shows that a filled logo wholly inside a box can survive as well.
(PyMuPDF's documentation describes COVERED and TOUCHED the other way round; the
code and the measurements here agree with each other, not with the docs.)

## What other tools do (`redaction-research.md`, sources there)

| Behaviour | Products |
|---|---|
| Cut paths at the box edge; only the covered part is destroyed | Adobe Acrobat, PDF-XChange, Apryse |
| Rasterise the page | LibreOffice Draw, PDF24 (both installed on this machine); Stirling-PDF optionally |
| Keep or remove whole subpaths | MuPDF / PyMuPDF (this app) |
| Leave vectors under the box | Nitro, Stirling-PDF area mode |

## Measured (`redaction_bench.py` → `redaction-bench.json`, PyMuPDF 1.28.2)

Eight test pages: a table cell, the same on a rotated page, a vector signature, a chart
line, an underline, a filled logo, a stroked circle and filled square, a shaded header
band. *Leak* = hidden ink still present when the box is applied without its black fill.
*Collateral* = visible ink changed outside the boxes.

| Strategy | worst leak | mean collateral | text outside still searchable | worst size |
|---|---|---|---|---|
| none (0) | 100 % | 0 % | 100 % | ×0.86 |
| **covered (1) — current** | **100 %** | 0 % | 100 % | ×0.86 |
| touched (2) | 0 % | 34 % (chart 82 %, signature 55 %) | 100 % | ×0.84 |
| clip at edge (prototype in the bench) | 0 % | ≤0.15 % | 100 % | ×1.19 |
| rasterise page | 0 % | 3 % | 0 % | ×50 |

`redaction_score.py` weights the four measurements plus precedent and implementation
risk (both judged, so swept rather than fixed) over all 4 095 weightings of 0–3:
**clip at edge wins 69 %** (71 % when leakage carries the highest weight), touched
19 %, rasterise 5 %. Clip loses only where implementation risk outweighs leakage.

## The prototype's limits

The clip strategy in `redaction_bench.py` removes touched paths with
`REMOVE_IF_TOUCHED`, then redraws the parts outside the boxes: strokes cut exactly
(curves flattened to 24 segments), filled rectangles cut exactly and redrawn beneath
the page content. Still open before it could ship: non-rectangular fills a box
touches are dropped, redrawn strokes move to the top of the drawing order, curves
become polylines, and shadings, patterns and clipping paths are not reproduced.
