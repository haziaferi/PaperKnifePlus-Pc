# Next session — owner-approved scope (2026-10-02)

Decided by the owner after the fresh-eyes audit (`fresh-eyes-2026-10-01.md`). Ids refer
to that register; each item still needs its own fail-before test, as in the audit.

## Already done in this session

- AGPL-3.0 licence (L5-49), Windows-only docs with MANUAL.md canonical (L4-07, L4-69).

## 1. Redaction: clip line art at the box edge (L3-18) — done 2026-10-07

`paperknife/lineart.py` cuts paths in place in the content stream (not the prototype's
remove-and-redraw); evidence in `docs/redaction/README.md`, tests in
`tests/test_redact_lineart.py`.

## 2. Responsiveness and structure

- RS-02: done 2026-10-08 (ef1dd92; measurements in `performance-2026-10-08.md`). A
  single save still holds the window for its length (PyMuPDF keeps the GIL); moving
  saves into a helper process would remove that — owner's call.
- RS-07 / RS-22 / L3-51: done 2026-10-08 (`paperknife/page_canvas.py`, bccf066). The
  cropped-page TextWriter fix was already in `pages.textwriter_point`.
- RS-13 / RS-14: shared file rows (adds drag and drop to 9 tools) and main buttons —
  these change sizes on screen, so show the owner the layout first.

## 3. Restore v2 features

L5-12 Find & Replace case / regex / whole-word · L5-04 Watermark page selector ·
L5-16 Merge Clear All · L5-17 Merge "drag to reorder" (build or reword) · L5-14 Ctrl+H ·
L5-11 Edit Text revert-span / reset page · L5-20 Open with… on recent files ·
L5-08 Compress size preview · L5-22 Edit Text in the Home quick actions.

## 4. Upstream tool gaps (PaperKnife+ Android)

L5-50 Delete pages · L5-51 Sign (signature image) · L5-52 Grayscale · L5-53 Compare.

## 5. PDF-tool parity

L5-55 Flatten · L5-56 Form filling · L5-57 Attachments · L5-54 Insert pages ·
L5-58 N-up / booklet · L5-60 Sanitise + subset fonts · L5-30 PDF/A via Ghostscript ·
L5-31 Linearise via qpdf · L5-59 pdfocr / "Make searchable" in Image → PDF.

## Still the owner's call (not in this scope)

L1-04 Ctrl+F target · L1-38 light-mode muted contrast · L2-33 Remove Password rules ·
L2-36 Normalise losing links · L3-09 edited-text font · L3-17 hyphenated search ·
L3-19 follow-up: a discard-changes prompt · L3-50 queue-based UI updates · L4-45 UPX ·
L4-46 measure installed size · L5-26 OCR language list · RS-06 follow-up: keep the
password on in-place saves.
