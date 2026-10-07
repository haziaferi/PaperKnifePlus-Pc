# Where the time goes: saves and background jobs (2026-10-08)

Measured with PyMuPDF 1.28.2 on Python 3.14, Windows 11. Scripts in
`../_step3-2026-10-08/` beside the repo (`gil_probe.py`, `garbage_scaling.py`,
`ocr_size.py`).

## Save settings

Every save ran in its own process with a 2-minute limit. Generated documents: text
pages (45 lines each), and the same with an image per page.

| text pages | plain | garbage=1 | garbage=2 | garbage=3 | garbage=3 deflate | garbage=4 | garbage=4 deflate clean |
|---|---|---|---|---|---|---|---|
| 100 | 0.36 s | 0.35 s | 0.26 s | 1.41 s | 1.92 s | > 120 s | 0.64 s |
| 200 | 0.86 s | 1.04 s | 4.61 s | 5.36 s | 6.19 s | > 120 s | 1.17 s |
| 400 | 1.34 s | 2.03 s | — | 23.9 s | 36.1 s | — | 2.27 s |
| 800 | 3.37 s | 4.04 s | — | > 120 s | > 120 s | — | 4.49 s |

With an image per page the shape is the same (800 pages: garbage=3 89 s,
garbage=4 deflate clean 4.3 s). A 2000-page file saved with garbage=4 deflate
(no clean) was still running after 25 minutes of CPU.

`garbage` 2 and 3 grow with the square of the page count, and garbage=4 without
`clean` is worse. garbage=1 removes every unreferenced object, which is all a
privacy-minded save needs (old content streams, replaced Info and XMP). garbage=4
with deflate and clean also merges duplicates, and stays near linear.

OCR-style output (the app's `add_text_layer`, 300 pages): garbage=3 deflate 2.50 s
and 3.46 MB; garbage=4 deflate clean 2.10 s and **0.95 MB**; garbage=1 deflate
0.79 s and 4.31 MB.

So: Metadata saves with garbage=1; OCR and Batch OCR with garbage=4, deflate and
clean, like Compress, PDF Tools and Redact. `tests/test_save_settings.py` fails on
any other setting.

## Background jobs and the GIL

A worker thread runs a long PyMuPDF operation while the main thread ticks every
10 ms (400 text pages):

| operation | alone | longest main-thread gap while it runs in a thread |
|---|---|---|
| `get_text("rawdict")`, page by page | 2.21 s | 36 ms |
| `search_for`, page by page | 0.95 s | 31 ms |
| render 60 pages | 0.40 s | 35 ms |
| one `save(garbage=4, deflate, clean)` | 0.50 s | **495 ms** |

PyMuPDF holds the GIL for the length of each call, so work done page by page in a
background job leaves the window responsive, with progress and Cancel, but one big
call (a save) freezes it for as long as it runs, background or not.
