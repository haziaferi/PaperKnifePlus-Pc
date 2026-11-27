# Purpose map

PaperKnife+ PC's screens grouped by purpose: what each screen does, where it sits in each window layout, and what it overlaps with. Overlaps were checked in the code (`paperknife/core`, `paperknife/qt/tools`, `paperknife/qt/structure.py`), not only in MANUAL.md. Each one is marked:

- **exact**: the same core call;
- **strong**: the same job, with a different way in;
- **medium**: a shared step inside different jobs;
- **weak**: they only look alike.

This is an assessment of the code at commit `567a365` (2026-11-27). It replaces the first map of 2026-10-17, whose decisions are listed under "Decided since the first map". SPEC.md holds the rules; this file explains why the screens are the ones they are. Nothing here changes a rule.

## Purposes

| | Purpose | Its job | Screens |
|---|---|---|---|
| P1 | **Open and read** | get to a document and look at it | 2 |
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

That is 24 screens: the 22 tools of `paperknife/tool_registry.py`, Preferences and Home. The first map counted 27; Split by Bookmarks, PDF → Images and one of the two "to PDF" screens have since been merged into others.

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

E2's groups follow the purposes more closely than the pane's: Batch leaves Organise for Files, and the pages tools sit together. Neither layout has a "Document structure" group: Bookmarks / TOC sits with the pages tools and Metadata with the file's protection (question 3).

## Screens whose purposes overlap

| | Strength | Screens | Why |
|---|---|---|---|
| O1 | exact | PDF Tools (Repair), Compress (Light) | `core.pdftools.repair_pdf` and `core.enhance.compress_pdf` at Light make the same `save(deflate=True, garbage=4, clean=True)` call; only Repair's message differs. Kept on purpose (2026-10-18): PDF Tools also sanitises, flattens and removes blank pages |
| O2 | strong | Batch; Compress, Watermark, OCR, PDF → Other | the same four jobs on a folder (`core.batch.TOOL_OPS`). Under E2, Batch runs prototype C and shows each tool's own settings panel (`qt/tool_options.PANELS`), so the settings cannot drift apart. Under the navigation pane it runs prototype A, with its own reduced settings (question 1) |
| O3 | strong | Rotate & Reorder; the page strip of Edit Text, Find & Replace, Annotate and Redact | turn, move and delete pages; the strip shares Rotate's delete question and Undo (2026-10-17) |
| O4 | strong | Rotate & Reorder ("Extract to a new PDF"), Split ("Selected pages to one part") | the selected pages into a new file; Split can also cut the rest into parts (question 2) |
| O5 | medium | Merge, Other → PDF | an ordered file list into one PDF; Merge takes only PDFs, Other → PDF only images and documents (`core.convert.TO_PDF_EXTS`) |
| O6 | medium | Edit Text, Find & Replace, Redact | find text and change it: one block, every match, or every match removed; Edit Text and Find & Replace share the reflow engine (`core.reflow`) |
| O7 | medium | Bookmarks / TOC, Split | both read the bookmark tree, one to edit it, one to cut at it |
| O8 | medium | Watermark, Header / Footer | text stamped on the selected pages: diagonal through the centre, or at a margin place with fields like `{page}` |
| O9 | medium | Normalise Pages, Crop / Trim | change a page's size: redraw onto a paper size, or cut the margins |
| O10 | medium | Metadata (clear all), PDF Tools (Sanitise, XMP metadata) | both take the document's properties out; Metadata edits them field by field |
| O11 | medium | PDF Tools (Remove blank pages), Rotate & Reorder (Delete) | remove pages: found as blank, or chosen |

Weak, and left as they are: Read / Preview and the editing workspaces both show the pages; PDF → Other's PNG / JPEG gives pictures of whole pages, Extract Images the images embedded in them; PDF Tools' Flatten bakes in what Annotate adds.

## What, and where

Each thing a person does, the places it can be done, and how it repeats. The places are not ranked.

| What | Places | Repeats |
|---|---|---|
| Open a recent file | Home's list; the document bar's Open arrow | 2 places |
| Rewrite the file clean | Compress (Light); PDF Tools (Repair); Batch (Compress) | 3 places |
| Watermark | Watermark; Batch | 2 places |
| OCR | OCR; Batch | 2 places |
| The text out | PDF → Other; Batch (PDF → Other) | 2 places |
| Turn, move or delete pages | Rotate & Reorder; the page strip in Edit Text, Find & Replace, Annotate, Redact | 5 places |
| Selected pages into a new file | Rotate & Reorder; Split | 2 places |
| Several files into one PDF | Merge (PDFs); Other → PDF (images, documents) | 2 places, different inputs |
| Find every occurrence of a phrase | Find & Replace; Redact | 2 places, different actions |
| See the bookmarks | Bookmarks / TOC; Split (Cut at bookmarks) | 2 places |
| Take the properties out | Metadata; PDF Tools (Sanitise) | 2 places |

There are 11 things done in more than one place, 26 places in all, so 15 places beyond the first for each thing. The first map had 10 things and 11 extra places. The repeats are now of a different kind: none is a whole screen held inside another. Most of the growth is the page strip, which the owner chose on 2026-10-17 so that an editor never has to leave its document to fix a page.

## How much

- **1 exact overlap** (O1), kept by the owner's choice.
- **3 strong overlaps.** Batch repeats four screens (O2); pages are turned, moved and deleted in two kinds of place (O3); the selected pages make a new file in two screens (O4).
- **7 medium overlaps.** They share a step but do different jobs; those screens stand on their own.
- **Measured against the 22 tool screens:** none is wholly contained in another (the first map found 2 of 25). Batch alone could become a mode of other screens (question 1).

## Decided since the first map

| First map item | Decision | Where it is now |
|---|---|---|
| O2 Split and Split by Bookmarks | one Split with "Cut at: page ranges / bookmarks" (owner, 2026-10-17) | Split; R26 |
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
2. **Selected pages into a new file** (O4): keep both Rotate & Reorder's "Extract to a new PDF" and Split's "Selected pages to one part", or keep one? Rotate's writes one file at once; Split's makes one part among others.
3. **Document structure** (P3): Bookmarks / TOC sits in Pages and Metadata in Protect & optimise under E2. Keep that, or give them a group of their own? Depends on R27.
