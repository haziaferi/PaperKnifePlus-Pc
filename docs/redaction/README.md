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
| **covered (1) — the app before L3-18** | **100 %** | 0 % | 100 % | ×0.86 |
| touched (2) | 0 % | 34 % (chart 82 %, signature 55 %) | 100 % | ×0.84 |
| clip at edge (prototype in the bench) | 0 % | ≤0.15 % | 100 % | ×1.19 |
| **clip at edge — shipped (`lineart.py`, 2026-10-07)** | **0 %** | **0.0 %** | 100 % | ×0.89 |
| rasterise page | 0 % | 3 % | 0 % | ×50 |

`redaction_score.py` weights the four measurements plus precedent and implementation
risk (both judged, so swept rather than fixed) over all 4 095 weightings of 0–3:
**clip at edge wins 69 %** (71 % when leakage carries the highest weight), touched
19 %, rasterise 5 %. Clip loses only where implementation risk outweighs leakage.

## What shipped (2026-10-07, `paperknife/lineart.py`)

The prototype removed touched paths and redrew the outside parts on top (strokes) or
underneath (fills), which is why it lost drawing order, non-rectangular fills,
shadings and clips. The shipped version **rewrites each touched path where it is** in
the content stream, so drawing order and every graphics-state setting stay:

- strokes are cut exactly at the box edge; Béziers stay Béziers (de Casteljau, in page
  space, mapped back through the inverse CTM); dashed strokes keep their phase;
- a fill or clip path with a **vertex** in a box (a bar whose hidden top is the
  secret, a logo), or with an edge that runs through a box and is visible nowhere
  else on the page, becomes the shape minus the boxes (curve-aware Sutherland–Hodgman
  against the four strips around each box; the winding number of every point outside
  the boxes is unchanged, so nonzero and even-odd both hold);
- a fill or clip path whose vertices all lie outside hides nothing in the box (what
  runs through it follows from what is visible; control points are off the path), so
  it is kept whole and painted, or intersected, through a clip that leaves the boxes
  out. Cutting it up instead changed MuPDF's rendering outside the boxes: tiling
  patterns re-tile and rectangle clips lose their pixel-exact edges;
- shadings are painted through that same clip;
- Form XObjects and soft-mask groups (`gs` → ExtGState `/SMask /G`, where Figma,
  Inkscape and Illustrator put shapes, and which MuPDF's redaction never visits) are
  rewritten into page-private copies; another page using the same form keeps it whole;
- operand counts and unknown keywords are read the way MuPDF reads them (measured).

Known cost: a rectangular clip with a corner inside a box is cut (the corner is
information), and MuPDF then anti-aliases its edges, so text sitting exactly on the
clip edge renders a little lighter (up to 152 px on one page of 104; `realworld.md`).

**Safety net.** After cutting, `lineart.residual()` reads the page back through
MuPDF's `get_drawings(extended=True)` and looks for a path vertex inside a box, a
stroke running through one, or a fill whose winding still covers a point in one after
the clips around it. If it finds any (a stream this module reads
differently from MuPDF), the page's original content is restored and MuPDF's
`REMOVE_IF_TOUCHED` is used instead. MuPDF's own removal does not reach soft-mask
groups, and nothing removes the positioned data of a mesh shading (types 4–7), so the
check runs again afterwards; if anything is still left, or the page uses a mesh
shading, the page becomes a picture of itself with its old resources dropped (what
LibreOffice and PDF24 always do). The Redact tool names such pages, and warns when a
page's text is no longer selectable. A content stream the module cannot read at all
takes the same path instead of failing.

Known effect, not a leak: a thick stroke cut at an angle keeps its butt cap, whose
corner reaches up to half the line width under the box. The ink belongs to the line
outside and the fill covers it (seen on Ghostscript's `text_graphic_image.pdf`: a
10 pt line, 8 px).

Not covered: tiling-pattern cells and Type3 glyph procedures (drawn per cell or glyph,
not at one page position) and annotation appearances (the tool deletes annotations
under a box).

Evidence: `tests/test_redact_lineart.py` (the eight bench cases plus drawing order,
dashes, even-odd, shading, clip path, forms shared and nested, a soft mask, bar tops,
rectangle cell clips, a tiling-pattern background, a rotated and cropped page, 60
boxes, stream syntax, wrong operand counts, malformed inline images, escaped names,
`gs` inside a path, an edge visible only in a box, dashes inherited by a form, a mesh
shading and the fallback), which fail on the code before L3-18 except the
drawing-order guard; an adversarial review of the engine (Opus), whose reproduced
findings are those last cases; `redaction_bench.py` (table above);
`realworld_check.py`, run over the PDFs that installed programs ship (Ghostscript,
PDF24, ONLYOFFICE, browsers), numbers in `realworld.md`.
