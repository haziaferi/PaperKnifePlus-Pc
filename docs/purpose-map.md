# Purpose map

PaperKnife+ PC's screens grouped by purpose: what each screen does, where it sits in each window layout, what it overlaps with, and how everyday jobs go through it. Overlaps were checked in the code (`paperknife/core`, `paperknife/qt/tools`, `paperknife/qt/structure.py`), not only in MANUAL.md, and the claims were checked again by a second, independent reader. Each overlap is marked:

- **exact**: the same core call;
- **strong**: the same job, with a different way in;
- **medium**: a shared step inside different jobs;
- **weak**: they only look alike.

This is an assessment of the code at commit `567a365` (2026-11-27). It replaces the first map of 2026-10-17, whose decisions are listed under "Decided since the first map". SPEC.md holds the rules; this file explains why the screens are the ones they are. Nothing here changes a rule.

## Purposes

| | Purpose | Its job | Screens |
|---|---|---|---|
| P1 | **Open, read and print** | get to a document, look at it, print it | 2 |
| P2 | **Rearrange pages** | which pages, in which file, in which order and turn | 3 |
| P3 | **Document structure** | the bookmark tree and the properties | 2 |
| P4 | **Stamp and resize pages** | put text on pages, or change the page size | 4 |
| P5 | **Change the content** | edit, replace, mark up or remove what is on the page | 4 |
| P6 | **Make it searchable** | turn scanned pages into text | 1 |
| P7 | **Look after the file** | size, damage, password | 3 |
| P8 | **Into PDF** | make a PDF from other files | 1 |
| P9 | **Out of PDF** | get pages, images or text out | 2 |
| P10 | **Many files at once** | one job over a folder | 1 |
| P11 | **The app** | how the app behaves | 1 |

That is 24 screens: the 22 tools of `paperknife/tool_registry.py`, Preferences and Home. The first map counted 27; Split by Bookmarks, PDF → Images and one of the two "to PDF" screens have since been merged into others. Printing is not a screen: the document bar's **Print** and `Ctrl+P` print the open document, with a page range, from every tool.

## Where each screen sits

The app has two window layouts until R27 is answered: the navigation pane (no `PK_*` switches; MANUAL.md section 5 describes it) and E2, the group rail with the floating card (`PK_STRUCT=workspace PK_PICKER=pane PK_FILES=window PK_DETAILS=float PK_LEFT=grouprail`). They group the screens differently.

| Screen | Purpose | Navigation pane group | E2 rail group |
|---|---|---|---|
| Home | P1 | (top) | (start screen) |
| Read / Preview | P1 | Read | the document workspace itself |
| Merge | P2 | Organise | Files |
| Split | P2 | Organise | Pages |
| Rotate & Reorder | P2 | Organise | Pages |
| Bookmarks / TOC | P3 | Organise | Pages |
| Metadata | P3 | Content | Protect & optimise |
| Watermark | P4 | Enhance | Content |
| Header / Footer | P4 | Enhance | Content |
| Normalise Pages | P4 | Enhance | Pages |
| Crop / Trim | P4 | Enhance | Pages |
| Edit Text | P5 | Content | Content |
| Find & Replace | P5 | Content | Content |
| Annotate | P5 | Content | Content |
| Redact | P5 | Content | Content |
| OCR | P6 | Content | Content |
| Compress | P7 | Enhance | Protect & optimise |
| PDF Tools | P7 | Enhance | Protect & optimise |
| Password | P7 | Enhance | Protect & optimise |
| Other → PDF | P8 | Convert | Files |
| PDF → Other | P9 | Convert | Convert |
| Extract Images | P9 | Convert | Convert |
| Batch | P10 | Organise | Files |
| Preferences | P11 | (bottom) | (bottom) |

Neither layout follows the purposes throughout:

- E2 groups by what a tool works on: one document (Pages, Content, Protect & optimise, Convert) or several files (Files). So it splits P2 between Pages and Files, and P4 between Pages (Normalise, Crop) and Content (Watermark, Header / Footer).
- The navigation pane keeps all of P4 together in Enhance, but mixes P2, P3 and P10 in Organise and puts Metadata in Content.
- Neither has a "Document structure" group (question 3).

## Screens whose purposes overlap

| | Strength | Screens | Why |
|---|---|---|---|
| O1 | exact | PDF Tools (Repair), Compress (Light) | `core.pdftools.repair_pdf` and `core.enhance.compress_pdf` at Light make the same `save(deflate=True, garbage=4, clean=True)` call. What differs: Repair always keeps the rewritten file and reports damage, Compress keeps it only when it is smaller (`qt/tools/compress.py` `size_report`). Kept on purpose (2026-10-18): PDF Tools also sanitises, flattens and removes blank pages |
| O2 | strong | Batch; Compress, Watermark, OCR, PDF → Other | the same jobs on a folder. Under E2, Batch runs prototype C: the four tools, each with its own settings panel (`qt/tool_options.PANELS`). Under the navigation pane it runs prototype A: Compress, Watermark, OCR and PDF → TXT only, with its own reduced settings (`core/batch.py` `OPS`). In both, Batch works on whole files, where the tools work on the selected pages, and Batch Compress writes its output even when it is not smaller (question 1) |
| O3 | strong | Rotate & Reorder; the page strip of Edit Text, Find & Replace, Annotate and Redact | turn, move and delete pages; the strip shares Rotate's delete question and Undo (owner, 2026-10-17) |
| O4 | strong | Rotate & Reorder ("Extract to a new PDF"), Split (a range such as `3-5`, or "Selected pages to one part"), Merge (one file, its pages kept or left out) | chosen pages into a new file, three ways: Rotate asks for a file name; Split writes into a folder with names it makes; Merge writes them in the order set in its strip (question 2) |
| O5 | medium | Merge, Other → PDF | an ordered file list into one PDF; Merge takes only PDFs, Other → PDF only images and documents (`core.convert.TO_PDF_EXTS`), so a PDF and photos cannot go into one file in one job (question 6) |
| O6 | medium | Edit Text, Find & Replace, Redact | find text and change it: one block, every match, or every match removed. Edit Text and Find & Replace share the reflow engine (`core.reflow`). Redact's search ignores capitals (`core/redact.py`); Find & Replace matches them as typed (R44) |
| O7 | medium | Bookmarks / TOC, Split | both read the bookmark tree, one to edit it, one to cut at it |
| O8 | medium | Watermark, Header / Footer | text stamped on the selected pages: diagonal through the centre, or at a margin place with fields like `{page}` |
| O9 | medium | Normalise Pages, Crop / Trim | change a page's size: redraw onto a paper size, or cut the margins |
| O10 | medium | Metadata (Clear all fields), PDF Tools (Sanitise) | Metadata empties the properties and drops the XMP copy of them; Sanitise drops only the XMP (`scrub(metadata=False)` in `core/pdftools.py`), so Title and Author stay |
| O11 | medium | PDF Tools (Remove blank pages), Rotate & Reorder (Delete) | remove pages: found as blank, or chosen |
| O12 | medium | Merge's page strip, Rotate & Reorder | move pages and leave them out; Merge does it on the way to a new file, Rotate on the open document |
| O13 | medium | OCR ("Text-only PDF"), PDF → Other (TXT) | the document's text as a new file: as a PDF of text pages, or as a text file |

Weak, and left as they are:
- Read / Preview and the editing workspaces both show the pages.
- PDF → Other's PNG / JPEG gives pictures of whole pages; Extract Images gives the images embedded in them.
- PDF Tools' Flatten bakes in what Annotate adds.
- Annotate's filled **Rectangle** looks like a Redact box but hides nothing: the text under it stays in the file. The two are in the same group in both layouts; Redact's own wording says what it removes (R42), Annotate's does not say what it keeps.

## What, and where

Each thing a person does, the places it can be done, and how it repeats. The places are not ranked.

| What | Places | Repeats |
|---|---|---|
| Open a recent file | Home's list; the document bar's Open arrow | 2 places |
| Rewrite the file clean | Compress (Light); PDF Tools (Repair); Batch (Compress) | 3 places |
| Watermark | Watermark; Batch | 2 places |
| OCR | OCR; Batch | 2 places |
| The text out | PDF → Other (TXT); Batch (PDF → TXT; under E2 every PDF → Other format); OCR (Text-only PDF) | 3 places |
| Turn, move or delete pages | Rotate & Reorder; the page strip in Edit Text, Find & Replace, Annotate, Redact; PDF Tools (Remove blank pages, delete only) | 6 places |
| Chosen pages into a new file | Rotate & Reorder; Split; Merge | 3 places |
| Several files into one PDF | Merge (PDFs); Other → PDF (images, documents) | 2 places, different inputs |
| Find every occurrence of a phrase | Find & Replace; Redact | 2 places, different actions |
| See the bookmarks | Bookmarks / TOC; Split (Cut at bookmarks) | 2 places |
| Take the properties out | Metadata (all of them); PDF Tools (Sanitise: XMP only) | 2 places, different reach |

There are 11 things done in more than one place, 29 places in all, so 18 places beyond the first for each thing. The first map had 10 things and 11 extra places. The repeats are now of a different kind: they are ways in from inside other jobs, not whole screens held inside one another. Most of the growth is the page strip, which the owner chose on 2026-10-17 so that an editor never has to leave its document to fix a page.

## How much

- **1 exact overlap** (O1), kept by the owner's choice.
- **3 strong overlaps.** Batch repeats four screens (O2); pages are turned, moved and deleted in two kinds of place (O3); chosen pages make a new file in three screens (O4).
- **9 medium overlaps.** They share a step but do different jobs; those screens stand on their own.
- **Measured against the 22 tool screens:** none does only what another screen already does (the first map found 2 of 25). Batch under E2 holds the four tools' settings panels and adds only the folder; it alone could become a mode of other screens (question 1).

## Everyday jobs

Fifteen common jobs walked through the code as it is, both layouts unless one is named.

**Work as the map describes:**
- print pages 2-4 (Print, with its page range);
- merge two PDFs (Merge);
- turn one sideways page while editing text (the page strip);
- shrink a file to email it (Compress);
- compress every PDF in a folder (Batch);
- add page numbers (Header / Footer);
- redact an ID number on several pages (Redact, Find & redact text, Mark all; a scan needs OCR first);
- send only pages 3-5 (three routes, O4).

**Work, by a longer route:**
- **Remove the open password:** the password is asked when the file opens and again as "Current password" before removal, then the file still has to be saved.
- **Strip the author before sharing:** Metadata, Clear all fields, Apply, Save. Sanitise looks like the place but leaves the author (O10).
- **OCR a scanned receipt, then search it:** OCR, Apply, then Find & Replace's Find All, which matches capitals as typed, so "total" misses "TOTAL". Read / Preview has no search, and `Ctrl+F` searches the tool names (question 5).
- **Combine a PDF with three phone photos:** Other → PDF for the photos, then Merge, with a file in between (question 6).

**Found and fixed** (2026-11-27, `docs/blank-scans-2026-11-27.md`):
- **Remove blank pages missed every blank scanned page:** it refused any page holding an image. It now finds a scanned page that shows only empty paper, and keeps one with any mark (R55).
- **Photos became pages as wide as their pixels:** a 4000 × 3000 photo made a page about 141 cm wide. A scan's page now takes the scanner's resolution, and a page larger than A4 is scaled down to fit it (R56). HEIC, a common phone format, is still not accepted: it needs a new library (question 7).

**Not in the app:** filling in or signing a form. Nothing writes form-field values, and Annotate has no ink, signature or image stamp; the nearest is a text box. SPEC.md neither lists it as a job (R01) nor rules it out (question 4).

## Decided since the first map

| First map item | Decision | Where it is now |
|---|---|---|
| O2 Split and Split by Bookmarks | one Split with "Cut at: page ranges / bookmarks" (owner, 2026-10-17) | Split (its range syntax in R26) |
| O1a PDF → Images inside PDF → Doc / Text | folded in, renamed "PDF → Other" (owner, 2026-10-18) | PDF → Other |
| O1b Image → PDF and Doc / Text → PDF | one ordered list, "Other → PDF" (owner, 2026-10-18) | Other → PDF |
| O1c PDF Tools = Compress at Light | PDF Tools stays, with Repair, Sanitise, Flatten, Remove blank pages (owner, 2026-10-18) | PDF Tools; O1 above |
| Pages on screen | thumbnails with selection on Merge, Split and the page-range tools; none on Compress (owner, 2026-10-17/18) | the page grids |
| Rotate & Reorder | gains Delete and "Extract to a new PDF" (owner, 2026-10-17) | O4, O11 above |
| Editors' pages | a page strip in Edit Text, Find & Replace, Annotate and Redact (owner, 2026-10-17/18) | O3 above |
| O3 Batch | prototypes A, B and C built and scored, parked until the window structure is chosen | still open: question 1 |
| Navigation groups | scored after the screens were decided | E2's rail groups; still open with R27 |
| Whole-app structure | scored and walked; E2 built and critiqued (2026-10-19 to 2026-11-22) | still open: R27 |

## Questions for the owner

1. **Batch** (O2): keep its own screen with each tool's full settings (prototype C, what E2 runs), its reduced settings (A, what the navigation pane runs), or a folder input on the four tools (B)? Depends on R27: C fits E2's Files group.
2. **Chosen pages into a new file** (O4): keep all three routes (Rotate's Extract, Split, Merge with one file), or point the job at one? Each writes differently: one named file, files in a folder, or one file in a set order.
3. **Document structure** (P3): Bookmarks / TOC sits in Pages and Metadata in Protect & optimise under E2. Keep that, or give them a group of their own? Depends on R27.
4. **Forms and signatures:** add filling in and signing a form as a job (R01), or rule it out (Out of scope)?
5. **Search in the document:** give Read / Preview a find (`Ctrl+F` in the document, ignoring capitals), or keep finding text to Find & Replace and Redact?
6. **PDFs and images in one job:** let Other → PDF take PDFs too (or Merge take images), or keep the two lists apart?
7. **HEIC photos:** accept them in Other → PDF? It needs the `pillow-heif` library in the app and the installer.
