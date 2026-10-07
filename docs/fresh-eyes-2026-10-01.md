# Fresh-eyes audit — PaperKnife+ PC 3.2.2 (2026-10-01)

Source audited: `paperknife_clean.zip` (v3.2.2), committed verbatim as tag `baseline`.
The quarantined single-file v2.1 copy that the session started in, and the six other
lineage copies, were used only to find lost features.

**347 findings · 301 fixed · 40 need your decision ·
1 withdrawn · 5 deferred · 0 handed off** — register built at `bccf066`.
Fixed by severity: 35 high, 110 medium, 147 low.

## How it was done

1. Five Opus reviewers read whole files (core, transform tools, content tools,
   docs ↔ code, lineage + upstream), each finding quoted at `file:line`; headline
   claims were reproduced by the coordinator before any fix.
2. `tests/conftest.py` drives the real tool views headless (hidden App, stubbed
   dialogs, isolated HOME). `PAPERKNIFE_SRC=<tree>` runs the suite against another
   source tree. Medium/high code fixes carry a test that fails on `baseline` (or,
   for review fixes, on `pre-review`) for the finding's own reason and passes at
   HEAD; the failing line is in `baseline_fail`. Where it is empty the `test`
   field says why: documentation and packaging fixes were checked against the
   code instead (evidence in `note`), and a few entries share another entry's test.
3. Six fix lanes on disjoint files, then two independent reviews of the whole
   diff — correctness (RC-*) and code-verification-core Pass 6/7 naturalness and
   security (RS-*) — fixed in a consolidation pass against tag `pre-review`.

`fresh-eyes-2026-10-01.jsonl` holds every row with quote, evidence, test and
baseline failure. Test names in it refer to the files as first written
(`test_fa.py`…`test_fe.py`); they were later renamed by subject.

Rows `V-*` come from the verifying pass of 2026-10-02 (real build, installer, Tesseract
and dependency floors); method and logs in `verification-2026-10-02.md`.

## Headline defects found in 3.2.2

- Watermark raised `bad rotate value` on every page; PDF/A and Linearise could
  never succeed on PyMuPDF 1.28 (both options removed).
- Redact, Edit Text, Find & Replace and Annotate crashed on open (a light/dark
  colour tuple passed to `tk.Canvas`).
- Every Doc→PDF conversion wrote pages until the disk filled (`Story.place()`
  unpacked backwards).
- Compress Medium/Aggressive rasterised every page, destroying text.
- Redaction left the secret in metadata, XMP, bookmarks, annotations, form
  fields and attachments, and missed on rotated pages.
- Drag and drop never loaded; the window title said v3.0.0.

## Fixed

| id | sev | file:line | what changed | test | commit |
|---|---|---|---|---|---|
| L1-01 | high | `paperknife/app.py:56` | tkdnd loaded with TkinterDnD._require(self) (adds bundled tkdnd dir to auto_path); wrong comment deleted; fai… | tests/test_fa.py::test_tkdnd_loads_and_file_row_is_a_drop_t… | 9055593 |
| L1-02 | high | `paperknife/app.py:292` | _filter_nav/_toggle_section re-pack the whole nav in registry order via _layout_nav instead of pack(after=<po… | tests/test_fa.py::test_search_clear_restores_every_section_… | 9055593 |
| L2-01 | high | `paperknife/tools/enhance.py:203` | New watermark_pdf(): insert_text with morph=(centre, Matrix(45 + page.rotation)) in unrotated page space, fon… | tests/test_watermark.py::test_watermark_writes_text_on_ever… | ebbdb57 |
| L2-02 | high | `paperknife/tools/batch.py:50` | Batch _do_watermark calls the shared enhance.watermark_pdf (same code as the tool). | tests/test_fb.py::test_batch_watermark_is_diagonal_and_hono… | ebbdb57 |
| L2-03 | high | `paperknife/tools/enhance.py:189` | Opacity slider value passed as fill_opacity/stroke_opacity (ExtGState /ca equals the slider). | tests/test_watermark.py::test_watermark_honours_opacity_and… | ebbdb57 |
| L2-05 | high | `paperknife/tools/enhance.py:37` | Medium/Aggressive no longer rasterise pages: compress_pdf() calls Document.rewrite_images with bicubic subsam… | tests/test_fb.py::test_compress_medium_resamples_images_and… | ebbdb57 |
| L2-07 | high | `paperknife/tools/pdftools.py:94` | PDF/A option, its level selector and the false 'requires PyMuPDF >= 1.24, upgrade' message removed; PDF Tools… | tests/test_fb.py::test_pdftools_default_run_saves_without_e… | ebbdb57 |
| L2-09 | high | `paperknife/tools/pdftools.py:85` | Linearise option removed. Verified: save(linear=True) on 1.28.2 raises FzErrorArgument 'Linearisation is no l… | tests/test_fb.py::test_pdftools_offers_no_linearise_or_pdfa | ebbdb57 |
| L2-10 | high | `paperknife/tools/batch.py:74` | Batch OCR writes the text layer as invisible words (render_mode=3) at Tesseract word boxes from image_to_data… | tests/test_fb.py::test_batch_ocr_writes_an_invisible_text_l… | ebbdb57 |
| L3-01 | high | `paperknife/tools/redact.py:118` | tk.Canvas bg=_tk_color(CANVAS_BG); the view now builds | tests/test_open_tools.py::test_tool_view_builds[RedactTool]… | 0d9d9d7 |
| L3-02 | high | `paperknife/tools/edit_text.py:68` | tk.Canvas bg=_tk_color(CANVAS_BG) | tests/test_open_tools.py::test_tool_view_builds[EditTextToo… | 0d9d9d7 |
| L3-03 | high | `paperknife/tools/find_replace.py:81` | tk.Canvas bg=_tk_color(CANVAS_BG); the current-hit outline also used the ACCENT tuple and now goes through _t… | tests/test_open_tools.py::test_tool_view_builds[FindReplace… | 0d9d9d7 |
| L3-04 | high | `paperknife/tools/annotate.py:128` | tk.Canvas bg=_tk_color(CANVAS_BG); the drag preview line/rectangle also passed the ACCENT tuple (TclError on … | tests/test_open_tools.py::test_tool_view_builds[AnnotateToo… | 0d9d9d7 |
| L3-05 | high | `paperknife/tools/edit_text.py:162` | block outlines use "" for none and _tk_color(ACCENT) when selected, in _render and _select_block | tests/test_fd.py::test_edit_apply_unchanged_keeps_text | 0d9d9d7 |
| L3-06 | high | `paperknife/tools/edit_text.py:193` | blocks read with get_text("dict") (spans carry 'text', images excluded by flags); a line's spans are joined w… | tests/test_fd.py::test_edit_select_shows_block_text; tests/… | 0d9d9d7 |
| L3-07 | high | `paperknife/tools/edit_text.py:261` | undo uses MuPDF's object journal (journal_enable on open, journal_start_op/stop_op around each Apply, journal… | tests/test_fd.py::test_edit_undo_restores_text_and_keeps_im… | 0d9d9d7 |
| L3-12 | high | `paperknife/tools/redact.py:219` | drawn boxes are mapped screen/zoom * page.derotation_matrix; pending boxes (drawn and searched) are drawn wit… | tests/test_fd.py::test_redact_box_on_rotated_page_covers_dr… | 0d9d9d7 |
| L3-14 | high | `paperknife/tools/redact.py:332` | Apply remembers each redacted phrase (search needle, or the text under a drawn box); Save runs _scrub_secrets… | tests/test_fd.py::test_redact_removes_secret_from_whole_file | 0d9d9d7 |
| L3-15 | high | `paperknife/tools/redact.py:266` | before apply_redactions, annotations and widgets intersecting a box are deleted and the page /Thumb is droppe… | tests/test_fd.py::test_redact_removes_secret_from_whole_file | 0d9d9d7 |
| L3-27 | high | `paperknife/tools/metadata.py:97` | Save deletes the XMP stream (del_xml_metadata) whenever the fields differ from what was loaded, and saves wit… | tests/test_fe.py::test_metadata_clear_all_also_removes_xmp | d73e486 |
| L3-33 | high | `paperknife/tools/convert.py:657` | The six copied Story loops replaced by one _write_story() helper that unpacks (more, filled) correctly and ch… | tests/test_fe.py::test_txt_to_pdf_short_text_finishes_on_on… | d73e486 |
| L4-01 | high | `paperknife/theme.py:16` | same as L1-36 | tests/test_fa.py::test_version_is_release | 9055593 |
| L4-13 | high | `MANUAL.md:145` | Enhance/deskew row deleted; ENHANCE rows list its 7 real tools | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-21 | high | `MANUAL.md:180` | Medium text matches the new code: images resampled to 150 DPI, JPEG q80, text kept | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-37 | high | `paperknife/tools/edit_text.py:68` | same fix as L3-01..04: bg=_tk_color(CANVAS_BG) in all four tools | tests/test_open_tools.py::test_tool_view_builds (4 params) … | 0d9d9d7 |
| L4-38 | high | `MANUAL.md:333` | Changelog line now says tkdnd loads through TkinterDnD._require and the build bundles it where that looks | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-47 | high | `build_windows.bat:82` | All three signtool calls use "!SIGNTOOL!" (quoted) | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-01 | high | `paperknife/tools/enhance.py:203` | Same as L2-01 (insert_text + morph rather than v2's TextWriter; both are valid in 1.28). | tests/test_watermark.py::test_watermark_writes_text_on_ever… | ebbdb57 |
| L5-02 | high | `paperknife/tools/batch.py:50` | Same as L2-02/L2-04: shared watermark_pdf with opacity. | tests/test_fb.py::test_batch_watermark_is_diagonal_and_hono… | ebbdb57 |
| L5-05 | high | `paperknife/tools/enhance.py:75` | Same as L2-05: per-image resampling via rewrite_images instead of page rasterisation (MuPDF's own image rewri… | tests/test_fb.py::test_compress_medium_resamples_images_and… | ebbdb57 |
| L5-06 | high | `paperknife/tools/enhance.py:68` | Same as L2-05: images are sized from their displayed DPI on the page by MuPDF's rewriter. | tests/test_fb.py::test_compress_aggressive_scales_images_to… | ebbdb57 |
| L5-09 | high | `paperknife/tools/edit_text.py:162` | duplicate of L3-05: outline="" for no outline | tests/test_fd.py::test_edit_apply_unchanged_keeps_text | 0d9d9d7 |
| L5-23 | high | `paperknife/tools/ocr.py:160` | Overlay mode edits a copy of the source: new add_text_layer() writes the words with TextWriter onto a one-pag… | tests/test_fe.py::test_ocr_overlay_keeps_original_page_and_… | d73e486 |
| RC-01 | high | `paperknife/tools/edit_text.py; paperknife/tools/find_replace.py:edit_text.py:117,155; find_replace.py:22,162` | Dropped MuPDF journalling; undo is a bounded (10) stack of whole-document snapshots (ToolBase._push_undo/_pop… | tests/test_review.py::test_edit_text_on_rotated_page_applie… | bc48149 |
| V-01 | high | `paperknife/tools/ocr.py:166` | ocr.tesseract(): PATH, then Program Files, Program Files (x86), %LOCALAPPDATA%\Programs. | tests/test_convert.py::test_ocr_finds_tesseract_in_its_defa… | 0a58896 |
| L1-03 | medium | `paperknife/app.py:343` | Delete binding goes through _on_delete_key, which ignores Entry/Text/TEntry/Spinbox widgets | tests/test_fa.py::test_delete_key_in_text_entry_does_not_re… | 9055593 |
| L1-06 | medium | `paperknife/app.py:418` | run_job refuses (showwarning 'Busy', returns None) while a job is running; stale on_done/on_cancel only hide … | tests/test_fa.py::test_second_job_is_refused_while_one_runs | 9055593 |
| L1-08 | medium | `paperknife/app.py:122` | _on_close asks to confirm when a job runs, cancels it and polls (not join) until the worker returns, max 15 s… | tests/test_fa.py::test_close_during_job_cancels_and_waits_f… | 9055593 |
| L1-11 | medium | `paperknife/app.py:731` | show_home uses entry.get('name') or Path(path).name; RecentFiles._load keeps only dicts with a str path | tests/test_fa.py::test_home_survives_recent_entry_without_n… | 9055593 |
| L1-25 | medium | `paperknife/prefs.py:43` | prefs/recent written through write_json_atomic (temp file + fsync + os.replace); Prefs.save raises OSError; S… | tests/test_fa.py::test_settings_save_reports_write_failure | 9055593 |
| L1-27 | medium | `paperknife/prefs.py:14` | OCR DPI slider starts from the Preferences DPI via prefs.pref_dpi(72, 400) (done by lane FE as HO-FA-1; ocr.p… | tests/test_convert.py (OCR preference tests) | d73e486 |
| L1-28 | medium | `paperknife/prefs.py:16` | OCR language field starts from PREFS.ocr_lang (done by lane FE as HO-FA-1; ocr.py:102) | tests/test_convert.py (OCR preference tests) | d73e486 |
| L1-30 | medium | `paperknife/recent.py:36` | _load keeps only dict entries with a str 'path' (non-list file -> []), so push cannot index a str | tests/test_fa.py::test_recent_wrong_shape_does_not_break_pu… | 9055593 |
| L1-31 | medium | `paperknife/recent.py:67` | entries with a non-str path are dropped at load; all() catches OSError from exists() | tests/test_fa.py::test_recent_wrong_shape_does_not_break_pu… | 9055593 |
| L1-36 | medium | `paperknife/theme.py:16` | theme.__version__ = '3.2.2' | tests/test_fa.py::test_version_is_release | 9055593 |
| L1-41 | medium | `paperknife/tools/settings.py:89` | max_recent must be 1..50 and default_dpi 72..600; non-numeric or out-of-range input shows a warning and nothi… | tests/test_fa.py::test_settings_rejects_out_of_range_max_re… | 9055593 |
| L2-04 | medium | `paperknife/tools/batch.py:43` | Batch opacity option now reaches watermark_pdf; colour stays the fixed grey (0.5,0.5,0.5), which is the singl… | tests/test_fb.py::test_batch_watermark_is_diagonal_and_hono… | ebbdb57 |
| L2-06 | medium | `paperknife/tools/enhance.py:93` | Saving computed from bytes, original size read before the save; when the output is not smaller the status is … | tests/test_fb.py::test_compress_never_reports_a_negative_sa… | ebbdb57 |
| L2-08 | medium | `paperknife/tools/pdftools.py:26` | The PDF/A-1b claim ('Embeds all fonts, sets colour profile') went with the option; subtitle now 'Repair corru… | tests/test_fb.py::test_pdftools_offers_no_linearise_or_pdfa | ebbdb57 |
| L2-11 | medium | `paperknife/tools/enhance.py:300` | show_pdf_page(..., keep_proportion=not stretch) so Stretch fills the target page. | tests/test_fb.py::test_normalise_stretch_fills_the_page | ebbdb57 |
| L2-12 | medium | `paperknife/tools/split.py:60` | Split parses ranges with the new shared paperknife.pages.parse_ranges, which rejects ranges past the end and … | tests/test_fc.py::test_split_rejects_pages_past_the_end; te… | 90e27b2 |
| L2-13 | medium | `paperknife/tools/split.py:63` | single pages go through parse_ranges: '99' -> 'page 99 does not exist (the document has 5 page(s))', '0' -> '… | tests/test_fc.py::test_split_rejects_pages_past_the_end; te… | 90e27b2 |
| L2-15 | medium | `paperknife/tools/merge.py:21` | every file's range is parsed with parse_ranges on the Tk thread before the save dialog; a reversed/out-of-ran… | tests/test_fc.py::test_merge_reports_a_reversed_range_inste… | 90e27b2 |
| L2-17 | medium | `paperknife/tools/crop.py:116` | crop.py and headerfooter.py both use FC's paperknife/pages.parse_ranges through one small helper crop.selecte… | tests/test_fb.py::test_crop_overlapping_ranges_crop_once | ebbdb57 |
| L2-18 | medium | `paperknife/tools/merge.py:96` | name button closes over its entry dict and looks up self._entries.index(entry) at click time | tests/test_fc.py::test_merge_name_click_selects_the_file_af… | 90e27b2 |
| L2-19 | medium | `paperknife/tools/bookmarks.py:97` | entries with page outside 1..len(doc) (get_toc's -1) are dropped and counted, the rest are sorted by start pa… | tests/test_fc.py::test_bookmark_split_skips_untargeted_entr… | 90e27b2 |
| L2-20 | medium | `paperknife/tools/toc.py:169` | when the chosen output is the open input (os.path.samefile) the TOC editor uses doc.saveIncr(), otherwise sav… | tests/test_fc.py::test_toc_saves_over_the_open_input | 90e27b2 |
| L2-26 | medium | `paperknife/tools/crop.py:126` | Margins are applied to the page as seen (page.rect) and mapped into the unrotated crop box with page.derotati… | tests/test_fb.py::test_crop_top_cuts_the_visible_top_of_a_r… | ebbdb57 |
| L2-31 | medium | `paperknife/tools/password.py:72` | Permissions start from all eight rights (_ALL_PERMS); unticking 'Allow printing' clears PRINT and PRINT_HQ, u… | tests/test_fb.py::test_password_allow_boxes_keep_unrelated_… | ebbdb57 |
| L2-32 | medium | `paperknife/tools/password.py:67` | Blank owner password now becomes a random secrets.token_urlsafe(24) owner password, so the open password give… | tests/test_fb.py::test_password_blank_owner_does_not_give_o… | ebbdb57 |
| L2-40 | medium | `paperknife/app.py:400` | same change as L1-07: on_done no longer covers the worker's own status | tests/test_fa.py::test_run_job_keeps_the_tools_status_messa… | 9055593 |
| L2-43 | medium | `MANUAL.md:179` | 5.8 Compress rewritten: Light = clean+deflate, Medium/Aggressive resample images above 150/96 DPI to JPEG q80… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L3-08 | medium | `paperknife/tools/edit_text.py:282` | apply_redactions(images=PDF_REDACT_IMAGE_NONE, graphics=PDF_REDACT_LINE_ART_NONE) in Edit Text and Find & Rep… | tests/test_fd.py::test_edit_apply_replaces_only_that_text_a… | 0d9d9d7 |
| L3-13 | medium | `paperknife/tools/annotate.py:209` | annotate _canvas_to_pdf applies derotation_matrix and the rect is normalized; edit_text block overlays/hit-te… | tests/test_fd.py::test_annotate_on_rotated_page_lands_under… | 0d9d9d7 |
| L3-16 | medium | `paperknife/tools/redact.py:266` | on Save, bookmark titles have the phrase stripped (set_toc keeps destinations) and attachments whose name/des… | tests/test_fd.py::test_redact_removes_secret_from_whole_file | 0d9d9d7 |
| L3-18 | medium | `paperknife/tools/redact.py:266` | Line art is cut at the box edge in place in the content stream (lineart.py), checked back through MuPDF (resi… | tests/test_redact_lineart.py (37); docs/redaction/realworld… | b15a501 |
| L3-19 | medium | `paperknife/tools/redact.py:156` | each view binds <Destroy> on its canvas to _close_doc(), so leaving the tool closes the document and releases… | tests/test_fd.py::test_leaving_tool_closes_document | 0d9d9d7 |
| L3-20 | medium | `paperknife/tools/find_replace.py:170` | replacement drawn with TextWriter at the first matched character's baseline origin, in that span's size and c… | tests/test_fd.py::test_replace_keeps_baseline_size_and_colo… | 0d9d9d7 |
| L3-21 | medium | `paperknife/tools/find_replace.py:164` | new module helper _find_matches searches the page's rawdict characters case-sensitively, joins lines with one… | tests/test_fd.py::test_replace_is_case_sensitive; tests/tes… | 0d9d9d7 |
| L3-23 | medium | `paperknife/tools/annotate.py:273` | rect fill is set_colors(fill=color) (3 numbers = RGB); opacity stays on set_opacity | tests/test_fd.py::test_annotate_rect_fill_is_rgb | 0d9d9d7 |
| L3-24 | medium | `paperknife/tools/annotate.py:253` | undo entry (page, ann.xref) is pushed only after the annotation exists; undo deletes exactly that xref and sk… | tests/test_fd.py::test_annotate_failed_add_then_undo_keeps_… | 0d9d9d7 |
| L3-25 | medium | `paperknife/tools/annotate.py:309` | a click (no drag) on an existing annotation selects it (dashed outline) instead of adding a new one; 'Remove … | tests/test_fd.py::test_annotate_click_selects_and_remove_de… | 0d9d9d7 |
| L3-29 | medium | `paperknife/tools/ocr.py:166` | hOCR regex replaced by pytesseract.image_to_data (new ocr_words()): words arrive unescaped, <strong>/<em> wor… | tests/test_fe.py::test_ocr_overlay_keeps_original_page_and_… | d73e486 |
| L3-30 | medium | `paperknife/tools/ocr.py:175` | Invisible text written with TextWriter (helv + MuPDF's built-in Noto fallback fonts for Greek/Cyrillic/CJK/Ar… | tests/test_fe.py::test_ocr_overlay_keeps_original_page_and_… | d73e486 |
| L3-31 | medium | `paperknife/tools/ocr.py:160` | Same change as L5-23: Overlay mode keeps the original page objects and adds the text layer onto them | tests/test_fe.py::test_ocr_overlay_keeps_original_page_and_… | d73e486 |
| L3-34 | medium | `paperknife/tools/convert.py:653` | Text stories use <pre> with user_css 'white-space: pre-wrap; font-size: 11pt' and are placed inside 36pt marg… | tests/test_fe.py::test_txt_to_pdf_long_text_wraps_and_spans… | d73e486 |
| L3-35 | medium | `paperknife/tools/convert.py:464` | RTF text escaped by _rtf_escape(): non-ASCII as signed 16-bit \uN? (surrogate pairs for astral), output encod… | tests/test_fe.py::test_pdf_to_rtf_keeps_non_latin1_characte… | d73e486 |
| L3-36 | medium | `paperknife/tools/convert.py:513` | PDF→XLSX cells written with data_type 's', so '=...' lines stay text | tests/test_fe.py::test_pdf_to_xlsx_does_not_create_formulas | d73e486 |
| L3-38 | medium | `paperknife/tools/convert.py:759` | XLSX→PDF renders '' only for None, so 0 / 0.0 / False are kept | tests/test_fe.py::test_xlsx_to_pdf_keeps_zero_cells | d73e486 |
| L3-39 | medium | `paperknife/tools/convert.py:88` | New _image_page() shared by Image→PDF and Doc→PDF PNG/JPEG: EXIF orientation applied, transparency flattened … | tests/test_fe.py::test_img2pdf_transparent_png_gets_white_b… | d73e486 |
| L3-47 | medium | `paperknife/tools/reader.py:218` | In-flight set keyed (gen, idx, zoom) stops re-queueing pages already requested; the worker skips requests out… | tests/test_fe.py::test_reader_does_not_rerender_pages_alrea… | d73e486 |
| L4-02 | medium | `setup.py:8` | setup.py reads __version__ from paperknife/theme.py by regex (no customtkinter import) | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-04 | medium | `README.md:1` | README title v3.2.2, archive named generically (real zip name unknown), v3.2.2 changelog added in Italian | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-05 | medium | `README.md:168` | 3.2.1 changelog line now says theme.py stayed at 3.0.0 until 3.2.2 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-07 | medium | `README.md:11` | owner chose Windows 10/11 only: README no longer claims macOS/Linux | none: docs | 5e5f356 |
| L4-12 | medium | `MANUAL.md:127` | Tools table regenerated: 26 rows, real labels, grouped by sidebar section, each pointing at its own 5.x subse… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-14 | medium | `MANUAL.md:144` | TOC row merged into 'Bookmarks / TOC' outline editor | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-15 | medium | `MANUAL.md:139` | Separate rows and subsections for Split by Bookmarks (5.5) and Bookmarks / TOC (5.6) | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-16 | medium | `MANUAL.md:146` | Batch row lists Compress, Watermark, OCR, PDF → TXT | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-17 | medium | `MANUAL.md:212` | 'Remaining tools' paragraph replaced by per-tool subsections; Batch described as folder-based | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-19 | medium | `MANUAL.md:163` | Same as L2-44 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-20 | medium | `MANUAL.md:179` | Light = clean + deflate, no image change | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-22 | medium | `MANUAL.md:181` | Aggressive = as Medium at 96 DPI, q80; no '60%' | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-23 | medium | `paperknife/tools/enhance.py:38` | Code now matches the Medium text: images are resampled to 150 DPI and recompressed as JPEG q80; text kept. Wo… | tests/test_fb.py::test_compress_medium_resamples_images_and… | ebbdb57 |
| L4-24 | medium | `MANUAL.md:185` | Annotate (now 5.18) lists the 7 real tools, Colour/Opacity/Zoom/Undo/click-to-select/Remove sel. | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-26 | medium | `MANUAL.md:192` | 5.15 says the language starts from Preferences and can be changed per run | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-27 | medium | `MANUAL.md:121` | 4.3 step 4 now true; adds that OCR and Batch → OCR start from the code | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-28 | medium | `README.md:110` | README sentence kept (now true) and extended: OCR and Batch OCR start from the code | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-29 | medium | `paperknife/tools/settings.py:66` | OCR, PDF to Images and PDF to Doc DPI defaults come from Preferences (lane FE HO-FA-1, shared pref_dpi after … | tests/test_convert.py::test_pdf2img_dpi_defaults_from_prefe… | d73e486 |
| L4-30 | medium | `MANUAL.md:193` | Overlay: original page kept, invisible words added; Text-only described separately | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-31 | medium | `MANUAL.md:197` | Same as L2-45 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-32 | medium | `MANUAL.md:201` | Same as L2-46 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-36 | medium | `MANUAL.md:251` | Troubleshooting row names which tools prompt for a password and which do not | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-39 | medium | `MANUAL.md:248` | DnD row split out with its own symptom and correct advice | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-42 | medium | `paperknife.spec:30` | tkdnd shipped as datas at tkinterdnd2/tkdnd/win-x64 (win-x64-tcl9 when the build Tcl is 9), that platform onl… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-53 | medium | `MANUAL.md:68` | Silent uninstall documented with _?=<instdir> and the leftover Uninstall.exe; build summary prints the same | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-54 | medium | `installer.nsi:106` | Section Main appends \PaperKnifePlusPC unless the chosen folder already ends with it; the uninstaller deletes… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-59 | medium | `requirements.txt:2` | PyMuPDF floor raised to 1.27.2 everywhere (setup.bat now installs from requirements.txt) | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-61 | medium | `setup.bat:19` | Checks Python >= 3.10, creates/reuses .venv, installs from requirements.txt into it, stops with an error afte… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-63 | medium | `MANUAL.md:223` | Delete row: Merge / Image → PDF only, ignored while typing | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-65 | medium | `README.md:163` | New App._ask_dir(title) and App._save_as(filetypes=) pass initialdir=PREFS.output_dir or None; Split, Split b… | tests/test_review.py::test_output_dialogs_start_in_the_pref… | bc48149 |
| L5-03 | medium | `paperknife/tools/enhance.py:189` | Same as L2-03. | tests/test_watermark.py::test_watermark_honours_opacity_and… | ebbdb57 |
| L5-07 | medium | `paperknife/tools/batch.py:25` | Batch compress uses the shared compress_pdf. | tests/test_fb.py::test_batch_compress_resamples_images_and_… | ebbdb57 |
| L5-10 | medium | `paperknife/tools/edit_text.py:81` | duplicate of L3-10: CTkTextbox read with get('1.0','end-1c') | none: see L3-10 | 0d9d9d7 |
| L5-13 | medium | `paperknife/tools/find_replace.py:170` | duplicate of L3-20: baseline origin, span size and colour | tests/test_fd.py::test_replace_keeps_baseline_size_and_colo… | 0d9d9d7 |
| L5-25 | medium | `paperknife/tools/ocr.py:57` | OCR DPI slider from PREFS.default_dpi (clamped 72-400); PDF→Images and PDF→Doc PNG/JPEG/PPTX DPI sliders from… | tests/test_fe.py::test_ocr_uses_preferences_language_and_dp… | d73e486 |
| L5-27 | medium | `paperknife/tools/annotate.py:108` | same fix as L3-25: click an annotation to select it, 'Remove sel.' deletes it | tests/test_fd.py::test_annotate_click_selects_and_remove_de… | 0d9d9d7 |
| L5-28 | medium | `paperknife/tools/annotate.py:253` | duplicate of L3-24: push (pg, xref) after a successful add, undo deletes that xref | tests/test_fd.py::test_annotate_failed_add_then_undo_keeps_… | 0d9d9d7 |
| L5-33 | medium | `paperknife/theme.py:16` | same as L1-36 | tests/test_fa.py::test_version_is_release | 9055593 |
| L5-36 | medium | `MANUAL.md:163` | Same as L2-44 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-37 | medium | `MANUAL.md:179` | Same as L2-43 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-38 | medium | `MANUAL.md:185` | Same as L4-24 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-42 | medium | `MANUAL.md:144` | Same as L4-14 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-43 | medium | `MANUAL.md:145` | Same as L4-13 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-45 | medium | `MANUAL.md:127` | Same as L4-12 (the registry has 26 tools including Preferences) | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-49 | medium | `MANUAL.md:349` | owner chose AGPL-3.0: LICENSE added (gnu.org text, sha256 0d96a4ff...), MANUAL 12 and setup.py say AGPL-3.0 | none: licence text hash checked | 5e5f356 |
| RC-02 | medium | `paperknife/tools/merge.py:168-200` | Each source is closed right after its pages are inserted; the merged file is saved through atomic_output; inp… | tests/test_review.py::test_merge_can_write_over_one_of_its_… | bc48149 |
| RC-03 | medium | `paperknife/tools/metadata.py:127-129` | New ToolBase._save_doc(out, **opts): saves through atomic_output; when out is the file self._doc was read fro… | tests/test_review.py::test_metadata_saves_over_the_open_inp… | bc48149 |
| RC-04 | medium | `paperknife/tools/rotate.py; bookmarks.py; toc.py; metadata.py (+ job_queue.py atomic_output):rotate.py:50-52; bookmarks.py:47-49; toc.py:77-79; metadata.py:90-91` | App._nav_click calls deactivate() on the previously active tool; ToolBase.deactivate closes self._doc; the fo… | tests/test_review.py::test_file_opened_in_another_tool_can_… | bc48149 |
| RC-06 | medium | `paperknife/tools/redact.py:277-281, 381-429` | Phrases from drawn boxes need >= 4 characters and match whole words only (typed search phrases keep substring… | tests/test_review.py::test_redact_box_over_short_text_leave… | bc48149 |
| RC-07 | medium | `paperknife/tools/find_replace.py:244-249` | pages.textwriter_point() corrects the origin for TextWriter.write_text, which offsets by the crop box top edg… | tests/test_review.py::test_replace_on_cropped_page_keeps_th… | bc48149 |
| RC-08 | medium | `paperknife/tools/convert.py:66-75` | _write_story returns False when place() reports the same overflowing filled rect on consecutive pages (overfl… | tests/test_review.py::test_html_with_unsplittable_row_stops… | bc48149 |
| RC-09 | medium | `paperknife/prefs.py:45-48` | prefs.json is read as bytes and decoded inside the try that renames unreadable files to .bad. | tests/test_review.py::test_prefs_file_that_is_not_utf8_is_r… | bc48149 |
| RS-01 | medium | `paperknife/tools/batch.py:182` | pages.render(page, scale, shrink) caps pixmaps at 100 MP: exports refuse with 'too large ... choose a lower D… | tests/test_review.py::test_render_refuses_or_shrinks_a_huge… | bc48149 |
| RS-06 | medium | `paperknife/job_queue.py:39` | Every final save goes through atomic_output. Tools holding the source use ToolBase._save_doc (or _release bef… | tests/test_review.py::test_content_tools_save_over_the_open… | bc48149 |
| RS-07 | medium | `paperknife/tools/edit_text.py:68` | Shared PageCanvasTool base (paperknife/page_canvas.py): file row, zoom, canvas, open, nav, render, save; tool… | tests/test_page_canvas.py; widget trees identical before/af… | bccf066 |
| RS-08 | medium | `paperknife/tools/merge.py:172` | selected_pages moved to pages.py (blank = every page, sorted unique); parse_ranges accepts 'all', so Merge (w… | tests/test_review.py::test_merge_accepts_all_as_its_placeho… | bc48149 |
| RS-09 | medium | `paperknife/tools/batch.py:21` | One spelling: app._open_pdf_safe everywhere; the ToolBase._open_safe forwarder is removed; converters and OCR… | see RC-13 | bc48149 |
| RS-10 | medium | `paperknife/tools/convert.py:648` | One module-level _FMTS and _NEEDS (lib, installed) dict, one _require() for the 'not installed' error, one _p… | tests/test_convert.py (unchanged, green) | bc48149 |
| RS-11 | medium | `paperknife/tools/convert.py:798` | XML fallback catches ET.ParseError and RTF fallback only ImportError, and the Done dialog/status say what fel… | tests/test_review.py::test_unparsable_xml_conversion_says_i… | bc48149 |
| V-02 | medium | `requirements.txt; setup.py:5; 23` | Floor 5.2.1; PyMuPDF 1.27.2 floor confirmed (176/176, then 183/183). Auditor F7. | venv on the floor versions: _verify-2026-10-02/ctk521-suite… | 93cca89 |
| V-04 | medium | `build_windows.bat:104-105` | Auditor F1; build2.log was started from another folder and succeeded. | tests/test_packaging.py::test_build_script_runs_from_its_ow… | 93cca89 |
| V-06 | medium | `installer.nsi:61-64` | Now exit 2 and nothing changed, both directions. Auditor F5. | live: Setup.exe /S and Uninstall.exe /S with the app open | ae36e9e |
| V-07 | medium | `installer.nsi:30` | Auditor F4. | live: install /D=<custom>, then /S | ae36e9e |
| V-16 | medium | `installer.nsi:74-85` | Owner's rule (2026-10-02): the app's own files may be deleted, nothing else. Found by the independent review … | live: shared folder with user files + old copy, setup then … | 37847a3 |
| L1-05 | low | `paperknife/app.py:339` | Ctrl+O/S/Z/K/F bound for both lower- and upper-case keysyms | none: keysym binding, verified by reading _bind_keys | 9055593 |
| L1-07 | low | `paperknife/app.py:399` | on_done shows a str result, else keeps a status the tool posted during the job (status sequence counter), els… | tests/test_fa.py::test_run_job_keeps_the_tools_status_messa… | 9055593 |
| L1-09 | low | `paperknife/app.py:380` | _clear_main calls _hide_tooltip first (also clears _last_hover_path so the pending after(400) does nothing) | none: tooltip timing; verified by reading | 9055593 |
| L1-10 | low | `paperknife/app.py:531` | hint drawn as a label placed over the empty readonly entry, hidden when the variable is set (CTkEntry never s… | tests/test_fa.py::test_tkdnd_loads_and_file_row_is_a_drop_t… | 9055593 |
| L1-12 | low | `paperknife/app.py:482` | unused App._register_drop deleted (grep: no callers) | none: dead code | 9055593 |
| L1-13 | low | `paperknife/app.py:12` | removed unused colorchooser, threading, PIL Image/ImageTk, CANVAS_BG imports (TkinterDnD is now used) | none: ruff F401 clean | 9055593 |
| L1-14 | low | `paperknife/app.py:367` | hasattr check and per-click inline import removed; dispatch is one inspect.signature test | none: refactor | 9055593 |
| L1-15 | low | `paperknife/app.py:617` | _save_as builds the filter from ext; duplicate local PREFS import dropped | none: trivial | 9055593 |
| L1-16 | low | `paperknife/app.py:634` | _open_pdf_safe returns None silently on Cancel/empty password; error only when authenticate fails | none: CTkInputDialog is modal and not stubbed by the harness | 9055593 |
| L1-17 | low | `paperknife/app.py:79` | forced light title-bar DWM block deleted; CTk sets it per mode at start and on set_appearance_mode | none: visual, Windows DWM | 9055593 |
| L1-18 | low | `paperknife/app.py:3` | docstring says 'collapsible sections + search'; unused sidebar_open pref deleted (stored copies are ignored b… | none: doc/dead pref | 9055593 |
| L1-19 | low | `paperknife/job_queue.py:86` | on_cancel keeps a status the worker posted (it finished past its last stop check) instead of overwriting it w… | none: race between Cancel and the worker's final stop check | 9055593 |
| L1-20 | low | `paperknife/job_queue.py:82` | CancellableJob posts through _post(), which drops RuntimeError/TclError raised by after() once the window is … | none: needs a destroyed mainloop window | 9055593 |
| L1-21 | low | `paperknife/job_queue.py:15` | on_done now uses the result (a str becomes the status message); docstring example updated | tests/test_fa.py::test_run_job_keeps_the_tools_status_messa… | 9055593 |
| L1-22 | low | `paperknife/tool_base.py:89` | unused ToolBase.run_job deleted (0 callers) | none: dead code | 9055593 |
| L1-23 | low | `paperknife/tool_base.py:84` | unused ToolBase._status deleted (0 callers) | none: dead code | 9055593 |
| L1-24 | low | `paperknife/tool_base.py:44` | docstring lists all six sections and says first-seen order sets sidebar order | none: doc | 9055593 |
| L1-26 | low | `paperknife/prefs.py:35` | unparsable or non-object prefs.json is renamed to prefs.json.bad; each stored key is type-checked against _DE… | tests/test_fa.py::test_prefs_load_validates_shape | 9055593 |
| L1-29 | low | `paperknife/prefs.py:17` | RecentFiles.all() slices to max_recent; the stored list is capped at RECENT_STORE_MAX=50, so lowering the set… | tests/test_fa.py::test_recent_max_zero_keeps_history | 9055593 |
| L1-32 | low | `paperknife/recent.py:42` | recent.json written atomically (write_json_atomic); only OSError is swallowed, since push runs inside tool wo… | none: covered by the prefs atomic test of the same helper | 9055593 |
| L1-33 | low | `paperknife/recent.py:28` | import-time APPDIR.mkdir removed; write_json_atomic creates the folder at save time and _save tolerates OSErr… | none: needs an unwritable home | 9055593 |
| L1-34 | low | `paperknife/recent.py:82` | thumbnail key is (path, size, mtime_ns); cache capped at 64 entries | none: low | 9055593 |
| L1-35 | low | `paperknife/recent.py:87` | thumbnail rendered at 2x the box and sized to fit it with the page's aspect ratio | none: visual | 9055593 |
| L1-37 | low | `paperknife/theme.py:51` | comment now says _tk_color resolves at call time and native widgets must be rebuilt after a mode change | none: comment | 9055593 |
| L1-39 | low | `paperknife/theme.py:47` | unused GREEN constant deleted (grep: only its definition) | none: dead code | 9055593 |
| L1-40 | low | `paperknife/tools/settings.py:18` | subtitle now 'Click Save Preferences to keep changes' | none: wording matches behaviour | 9055593 |
| L1-42 | low | `paperknife/tools/settings.py:60` | Colour mode row reads PREFS.appearance (keeps 'system') instead of ctk.get_appearance_mode() | none: low | 9055593 |
| L1-43 | low | `paperknife/tools/settings.py:99` | Restore copies _DEFAULTS (except window_geometry) into PREFS, applies the mode, saves, and re-renders the view | none: low | 9055593 |
| L1-44 | low | `paperknife/tools/settings.py:102` | Restore uses prefs._DEFAULTS instead of a hand copy | none: low | 9055593 |
| L2-14 | low | `paperknife/tools/split.py:59` | Split accepts 'end' and tolerates empty parts ('1,,3') via the shared parser; bad tokens get a readable messa… | tests/test_fc.py::test_split_writes_the_pages_it_names; tes… | 90e27b2 |
| L2-16 | low | `paperknife/tools/headerfooter.py:153` | Header/Footer uses the shared parser (paperknife/pages.parse_ranges via crop.selected_pages), case-insensitiv… | tests/test_fb.py::test_headerfooter_accepts_capitalised_end | ebbdb57 |
| L2-21 | low | `paperknife/tools/toc.py:157` | Delete promotes the removed entry's descendants one level; Save checks the hierarchy (each row at most one le… | tests/test_fc.py::test_toc_delete_parent_promotes_children | 90e27b2 |
| L2-22 | low | `paperknife/tools/toc.py:130` | Add/Update share _read_fields, which requires an open PDF and 1 <= page <= len(doc) | tests/test_fc.py::test_toc_rejects_page_past_the_end | 90e27b2 |
| L2-23 | low | `paperknife/tools/toc.py:77` | show() closes any document still held from the previous visit before resetting self._doc | tests/test_fc.py::test_navigating_away_closes_the_open_docu… | 90e27b2 |
| L2-24 | low | `paperknife/tools/rotate.py:64` | _open opens the new file (via app._open_pdf_safe) first and closes the old document only on success | tests/test_fc.py::test_rotate_keeps_document_when_reopen_fa… | 90e27b2 |
| L2-25 | low | `paperknife/tools/rotate.py:94` | thumbnails are sized from the pixmap to fit 100x130 keeping aspect (landscape and 90/270 rotations no longer … | tests/test_fc.py::test_rotate_thumbnail_keeps_aspect | 90e27b2 |
| L2-27 | low | `paperknife/tools/crop.py:139` | Negative margins refused up front with a warning; only pages actually cropped are counted, skipped pages name… | tests/test_fb.py::test_crop_negative_margin_is_refused_up_f… | ebbdb57 |
| L2-28 | low | `paperknife/tools/crop.py:74` | Checkbox relabelled 'Reset to full media box first (undo previous crops)' - what set_cropbox(page.mediabox) r… | none: label text only | ebbdb57 |
| L2-29 | low | `paperknife/tools/headerfooter.py:138` | Non-numeric Size/Margin now shows a warning and stops, like Crop, instead of silently using 10/20. | tests/test_fb.py::test_headerfooter_bad_size_warns_instead_… | ebbdb57 |
| L2-30 | low | `paperknife/tools/headerfooter.py:176` | Dead is_center assignment deleted. | none: dead local (ruff F841) | ebbdb57 |
| L2-34 | low | `paperknife/tools/password.py:75` | Protect on an already-encrypted input authenticates with the 'Current password' field first; wrong/blank pass… | tests/test_fb.py::test_password_change_on_an_encrypted_file | ebbdb57 |
| L2-35 | low | `paperknife/tools/pdftools.py:79` | Second fitz.open(filetype='pdf') and its misleading 'repair flag' comment removed; one open, garbage=4/clean/… | tests/test_fb.py::test_pdftools_repair_recovers_a_truncated… | ebbdb57 |
| L2-37 | low | `paperknife/tools/enhance.py:206` | No-op page.draw_rect(color=None, fill=None) deleted (the whole old watermark loop was replaced). | none: dead drawing op | ebbdb57 |
| L2-38 | low | `paperknife/tools/batch.py:208` | Size/DPI/opacity validated on the main thread before the job; invalid values show one warning and nothing run… | tests/test_fb.py::test_batch_rejects_bad_numeric_options_up… | ebbdb57 |
| L2-39 | low | `paperknife/tools/batch.py:17` | Batch compress and watermark call enhance.compress_pdf / enhance.watermark_pdf; the duplicated rasterising co… | tests/test_fb.py::test_batch_compress_resamples_images_and_… | ebbdb57 |
| L2-41 | low | `paperknife/app.py:418` | same change as L1-06: run_job refuses while a job runs | tests/test_fa.py::test_second_job_is_refused_while_one_runs | 9055593 |
| L2-42 | low | `paperknife/tools/merge.py:171` | Merge, Split, Rotate and Split-by-Bookmarks open inputs with app._open_pdf_safe on the Tk thread (password pr… | none: the password prompt is a CTkInputDialog the harness d… | 90e27b2 |
| L2-44 | low | `MANUAL.md:163` | 5.3 Split: comma ranges, each range one file; blank = one PDF per page into a chosen folder; no checkbox/ZIP | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L2-45 | low | `MANUAL.md:197` | 5.4 Rotate & Reorder: single thumbnail selection, CCW/CW/180, Move Left/Right; no multi-select or Rotate All | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L2-46 | low | `MANUAL.md:201` | 5.12 Crop: margins in points, page range, reset checkbox, no preview | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L2-47 | low | `MANUAL.md:212` | 5.7 Batch lists its four operations, output names and folder behaviour | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L2-48 | low | `MANUAL.md:144` | Table row and 5.6 describe Bookmarks / TOC as an outline editor that creates no TOC page | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L3-10 | low | `paperknife/tools/edit_text.py:81` | edit field is a multi-line CTkTextbox (read with get('1.0','end-1c')); the StringVar is gone | none: widget swap; exercised by every tests/test_fd.py::tes… | 0d9d9d7 |
| L3-11 | low | `paperknife/tools/edit_text.py:25` | deleted the never-shown CTkImage conversion per render, the _tk_img/_sel_span/_edit_var attributes and the un… | none: dead code; ruff F clean | 0d9d9d7 |
| L3-22 | low | `paperknife/tools/find_replace.py:97` | Replace All runs as one journal op; app._cur_undo_fn = _undo calls journal_undo (Ctrl+Z) | tests/test_fd.py::test_replace_can_be_undone | 0d9d9d7 |
| L3-26 | low | `paperknife/tools/annotate.py:30` | MANUAL 5.18 lists the seven annotation tools, colour/opacity/zoom, click-to-select and Remove sel.; no freeha… | none: docs, checked against annotate.py | e500b75 |
| L3-28 | low | `paperknife/tools/metadata.py:18` | Date fields accept YYYY-MM-DD[ HH:MM[:SS]] (converted to D:YYYYMMDDHHmmSS) or a D: date; anything else shows … | tests/test_fe.py::test_metadata_date_field_converted_to_pdf… | d73e486 |
| L3-32 | low | `paperknife/tools/ocr.py:57` | Language entry pre-filled from PREFS.ocr_lang | tests/test_fe.py::test_ocr_uses_preferences_language_and_dpi | d73e486 |
| L3-37 | low | `paperknife/tools/convert.py:478` | XML-illegal control characters stripped (_XML_ILLEGAL) before add_paragraph and XLSX cell writes; DOCX now ge… | tests/test_fe.py::test_pdf_to_docx_survives_control_charact… | d73e486 |
| L3-40 | low | `paperknife/tools/convert.py:665` | HTML story gets archive=fitz.Archive(<html file folder>) so relative images/CSS resolve | tests/test_fe.py::test_html_to_pdf_resolves_relative_images | d73e486 |
| L3-41 | low | `paperknife/tools/convert.py:716` | DOCX→PDF walks the body in document order; Title/Heading 1-3+ map to h1-h3, tables become <table> with border… | tests/test_fe.py::test_docx_to_pdf_keeps_document_order | d73e486 |
| L3-42 | low | `paperknife/tools/convert.py:489` | PDF→PPTX fits each page picture inside the slide, centred, keeping its aspect ratio | tests/test_fe.py::test_pdf_to_pptx_keeps_page_aspect | d73e486 |
| L3-43 | low | `paperknife/tools/convert.py:268` | Extract Images converts modes PNG cannot store (CMYK) to RGB, counts per-image failures and reports them in t… | none: could not reproduce the CMYK failure here (PyMuPDF 1.… | d73e486 |
| L3-44 | low | `paperknife/tools/convert.py:443` | PDF→XML: dead prolog strip and wrong comment removed; each page's own <page id=...> element is emitted direct… | tests/test_fe.py::test_pdf_to_xml_is_well_formed_without_ne… | d73e486 |
| L3-45 | low | `paperknife/tools/convert.py:185` | ExtractTool.show and Doc2PdfTool.show set app._cur_open_fn (PDF picker / _pick); the unused 'app' locals are … | tests/test_fe.py::test_ctrl_o_opens_a_file_in_converter | d73e486 |
| L3-46 | low | `paperknife/tools/convert.py:648` | Doc→PDF creates the in-memory document only in the PPTX and PNG/JPEG branches that use it | none: dead-code removal | d73e486 |
| L3-48 | low | `paperknife/tools/reader.py:144` | Page rects are read once in _load before the worker can see the document; _layout_pages and the page counts u… | none: a two-thread race on the Document is not deterministi… | d73e486 |
| L3-49 | low | `paperknife/tools/reader.py:59` | Zoom slider kept as self._zoom_slider and set to self._zoom | tests/test_fe.py::test_reader_zoom_slider_shows_current_zoom | d73e486 |
| L3-51 | low | `paperknife/tools/redact.py:287` | The four canvas tools share one viewer (see RS-07); found on the way: Edit Text kept a stale selection across… | tests/test_page_canvas.py; widget trees identical before/af… | bccf066 |
| L4-03 | low | `setup.bat:3` | Banner says v3.2.2 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-06 | low | `MANUAL.md:343` | 'Initial public release' replaced by a pointer to README's 3.2.1 changelog | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-08 | low | `README.md:151` | macOS hint now says Apple's python3 (3.9) is below the 3.10 minimum | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-09 | low | `README.md:20` | README uses the real folder name PaperKnifePlusPC (steps, venv comment, file tree) | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-10 | low | `MANUAL.md:270` | 9.2 step 1: folder renamed PaperKnifePlusPC; the parentheses/spaces warning and its stale cause removed; repl… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-11 | low | `MANUAL.md:97` | 4.1 says seven quick actions and names them | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-18 | low | `MANUAL.md:210` | Each tool has its own heading 5.1-5.26; Preferences is 5.26 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-25 | low | `MANUAL.md:133` | Annotate row: 'Highlights, shapes, notes, and text boxes' | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-33 | low | `MANUAL.md:153` | 5.2 uses '＋ Add PDFs', '✕ Remove selected', and drop onto the list when DnD is available | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-34 | low | `MANUAL.md:173` | Warning reworded: without the password the file cannot be opened; lost passwords cannot be recovered | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-35 | low | `MANUAL.md:170` | 5.11 names the two checkboxes and the random owner password when blank | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-40 | low | `MANUAL.md:248` | Stale build_windows.bat row deleted | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-41 | low | `MANUAL.md:89` | 3.3 note lists DOCX/PPTX/XLSX conversion and RTF → PDF text extraction as disabled without the libraries | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-43 | low | `paperknife.spec:12` | WIN-BLD-01 comment now says debug=False, symbols not stripped | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-44 | low | `paperknife.spec:49` | collect_data_files('customtkinter') adds the themes, fonts and icons explicitly | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-48 | low | `build_windows.bat:92` | Signing loop covers *.dll and *.pyd and stops on the first failure; installer signing checks errorlevel; fail… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-49 | low | `build_windows.bat:8` | PFX password read from the PFX_PASSWORD environment variable; a second command-line argument is refused; manu… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-50 | low | `build_windows.bat:121` | Installer and silent-test lines printed only when makensis ran (MADE_INSTALLER) | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-51 | low | `MANUAL.md:47` | 3.1 and 9.1 say NSIS absence skips Steps 4–5 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-52 | low | `build_windows.bat:14` | Header now says build from a clean venv, never conda/global, matching MANUAL 9.1; the script refuses to run o… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-55 | low | `installer.nsi:65` | UninstallString has no /S (confirm page shows); /S kept in QuietUninstallString | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-56 | low | `installer.nsi:119` | False 'Uninstall dialog can optionally prompt' comment removed | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-57 | low | `MANUAL.md:337` | Changelog: manifest embedded in PaperKnifePlusPC.exe | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-58 | low | `app.manifest:13` | Windows 8.1 supportedOS GUID removed; only the Win10/11 GUID remains, matching the comment and MANUAL's Windo… | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-60 | low | `paperknife/recent.py:12` | every module imports pymupdf as fitz; the start-up deprecation warning is gone (launch log empty) | none: launch check, empty log | 8821db5 |
| L4-62 | low | `run.bat:2` | cd /d "%~dp0", uses .venv\Scripts\python.exe when present, pauses on a non-zero exit | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-64 | low | `paperknife/tools/settings.py:18` | same as L1-40 | none: wording | 9055593 |
| L4-66 | low | `MANUAL.md:323` | recent.json described as path, file name, size, page count, access time | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-67 | low | `MANUAL.md:325` | Privacy section mentions first-page thumbnails on Home and in hover previews | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L4-68 | low | `paperknife/app.py:73` | same as L1-17 | none: visual | 9055593 |
| L4-69 | low | `README.md:116` | owner chose MANUAL.md (English) as the canonical manual; README is a short Italian summary linking to it; v3.… | none: docs | 5e5f356 |
| L5-15 | low | `paperknife/tools/merge.py:45` | each merge row's name button binds <Enter>/<Leave> to app._show_tooltip/_hide_tooltip with the same 400 ms de… | none: hover needs real pointer events on a mapped window; C… | 90e27b2 |
| L5-18 | low | `paperknife/app.py:482` | same as L1-12 | none: dead code | 9055593 |
| L5-19 | low | `paperknife/tools/convert.py:599` | Doc→PDF file row (frame, entry and its inner widget) registered as tkdnd drop targets; a drop goes through th… | none: tkdnd drop events cannot be driven headless | d73e486 |
| L5-24 | low | `paperknife/tools/ocr.py:166` | Words with Tesseract confidence < 30 are dropped (v2 parity) and text is unescaped (image_to_data) | tests/test_fe.py::test_ocr_overlay_keeps_original_page_and_… | d73e486 |
| L5-29 | low | `paperknife/app.py:77` | same as L1-17: CTk sets the DWM dark flag per mode and re-applies it on set_appearance_mode | none: visual | 9055593 |
| L5-32 | low | `paperknife/tools/pdftools.py:79` | Same as L2-35: single open, misleading comment gone, doc.is_repaired reported. | tests/test_fb.py::test_pdftools_repair_recovers_a_truncated… | ebbdb57 |
| L5-34 | low | `README.md:1` | Same as L4-04 / L4-03 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-35 | low | `MANUAL.md:97` | Same as L4-11 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-39 | low | `MANUAL.md:197` | Same as L2-45 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-40 | low | `MANUAL.md:201` | Same as L2-46 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-41 | low | `MANUAL.md:207` | 5.22 PDF → Images: PNG only, DPI 72–300, ZIP; JPEG pages are under PDF → Doc / Text (5.24) | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-44 | low | `MANUAL.md:146` | Same as L4-16; Batch Watermark now uses enhance.watermark_pdf (no rotate=45), grey | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-46 | low | `MANUAL.md:171` | 5.11 describes the separate Remove Password panel | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-47 | low | `MANUAL.md:248` | Same as L4-40 / L4-39 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| L5-48 | low | `MANUAL.md:270` | Same as L4-09 / L4-10 | none: docs lane; claim checked against code, evidence in no… | e500b75 |
| RC-05 | low | `paperknife/job_queue.py:58-60` | os.replace moved inside the try: a failed replace deletes the .part and re-raises; PermissionError is re-rais… | tests/test_review.py::test_atomic_output_removes_its_temp_f… | bc48149 |
| RC-10 | low | `paperknife/tools/batch.py; paperknife/app.py:batch.py:201-223; app.py:426-431` | A cancelled batch posts 'Batch cancelled after N of M file(s) - x OK, y errors' in WARN. | tests/test_review.py::test_cancelled_batch_does_not_report_… | bc48149 |
| RC-11 | low | `paperknife/tools/edit_text.py; paperknife/tools/find_replace.py:edit_text.py:263-268; find_replace.py:224-226` | The snapshot is taken before the edit; on any failure it is restored at once and the error shown. | tests/test_review.py::test_failed_edit_puts_the_original_te… | bc48149 |
| RC-12 | low | `tests/test_fc.py:232-240` | test_navigating_away_closes_the_open_documents now navigates to CropTool and covers all eight holders. | tests/test_organise.py::test_navigating_away_closes_the_ope… | bc48149 |
| RC-13 | low | `paperknife/tools/ocr.py; paperknife/tools/convert.py:ocr.py:177; convert.py:225,302,486` | OCR, PDF->Images, Extract Images and PDF->Doc open the input with app._open_pdf_safe on the Tk thread (passwo… | tests/test_review.py::test_pdf_to_images_unlocks_a_protecte… | bc48149 |
| RS-03 | low | `paperknife/tools/ocr.py:209` | OCR saves into atomic_output's temp file after the loop (no second in-memory copy; the source still closes be… | tests/test_convert.py OCR tests (unchanged, green) | bc48149 |
| RS-04 | low | `paperknife/job_queue.py:51` | atomic_output keeps the mkstemp file instead of unlinking it; an empty temp file at exit means the worker wro… | tests/test_shell.py::test_atomic_output_keeps_existing_file… | bc48149 |
| RS-12 | low | `paperknife/tools/metadata.py:81` | One lifetime rule: the held document is closed by deactivate() when the tool is left (see RC-04); Metadata no… | tests/test_organise.py::test_navigating_away_closes_the_ope… | bc48149 |
| RS-15 | low | `paperknife/tools/redact.py:38` | theme.py gains WARN_BG/WARN_TITLE/WARN_BODY (light, dark), HIT/HIT_CUR/HIT_EDGE and ON_ACCENT; the three ambe… | tests/test_open_tools.py::test_home_and_tools_both_modes | bc48149 |
| RS-16 | low | `paperknife/tools/merge.py:200` | Every after(0, lambda: [...]) / tuple callback is now a named local function. | full suite | bc48149 |
| RS-17 | low | `paperknife/tools/pdftools.py:25` | The one-option radio and self._op are replaced by a bold label; test asserts no radio and no Linearise/PDF-A … | tests/test_enhance.py::test_pdftools_offers_no_linearise_or… | bc48149 |
| RS-18 | low | `paperknife/tools/batch.py:192` | _OPS maps name -> function; the a = attr rebinding is gone; _make_opt creates its StringVar once. | tests/test_enhance.py batch tests | bc48149 |
| RS-19 | low | `paperknife/tool_base.py:79` | Removed the unused ToolBase._listbox, _big_btn, _save_as and _open_safe forwarders. | full suite | bc48149 |
| RS-20 | low | `paperknife/tools/redact.py:248` | Comment at the search_for call: case-insensitive over-marking is the safe side for redaction; Find & Replace … | none: comment only | bc48149 |
| RS-21 | low | `paperknife/job_queue.py:48` | write_json_atomic is built on job_queue.atomic_output (open tmp, dump, fsync); one atomic-write helper. | tests/test_shell.py::test_prefs_atomic_write_leaves_old_fil… | bc48149 |
| RS-22 | low | `paperknife/tools/annotate.py:219` | One page<->screen mapping in PageCanvasTool (_screen_matrix, _page_to_screen, _screen_to_page, _screen_rect_t… | tests/test_page_canvas.py; widget trees identical before/af… | bccf066 |
| RS-23 | low | `paperknife/tools/headerfooter.py:166` | Removed the named narrating comments and the restating docstring; the three header/footer position flags are … | none: comments | bc48149 |
| RS-24 | low | `paperknife/tools/redact.py:26` | Mutable class attributes (_blocks, _hits, _pending, _secrets, _page_rects) are initialised per view. | full suite | bc48149 |
| RS-25 | low | `paperknife/app.py:738` | app._open_pdf_safe records the file in Recent; the per-tool RECENT.push calls are removed, so every tool that… | full suite | bc48149 |
| RS-26 | low | `paperknife/job_queue.py:88` | Workers are always called as fn(stop); the signature sniffing and the unused stop property are gone; _nav_cli… | tests/test_shell.py job tests | bc48149 |
| RS-27 | low | `paperknife/tools/__init__.py:18` | tools/__init__.py imports modules only, without the stale stars; customtkinter, PREFS and PIL imports moved t… | tests/test_open_tools.py | bc48149 |
| RS-28 | low | `tests/conftest.py:157` | test_fa..fe renamed to test_shell/enhance/organise/content/convert with subject docstrings; 'import pymupdf a… | full suite | bc48149 |
| V-03 | low | `paperknife/app.py:63` | Auditor F6; spec now bundles assets/icon.ico. | tests/test_packaging.py::test_window_uses_the_app_icon_not_… | 93cca89 |
| V-05 | low | `build_windows.bat:20-21` | Comment corrected; the signing method is decision V-16. |  | 93cca89 |
| V-08 | low | `installer.nsi:64` | Auditor F5. | live: planted _internal\STALE-from-old-build.txt, upgrade | ae36e9e |
| V-09 | low | `installer.nsi:134` | Uninstall left an empty HKCU\Software\potatameister key. | live: install then uninstall | ae36e9e |
| V-10 | low | `installer.nsi:-` | RunningX64 check in .onInit; not run (no 32-bit Windows). Auditor F13. |  | ae36e9e |
| V-11 | low | `installer.nsi:33` | ManifestDPIAware true. Auditor F11. |  | ae36e9e |
| V-12 | low | `installer.nsi:9` | Auditor F20. |  | ae36e9e |
| V-13 | low | `installer.nsi; build_windows.bat; version_info.txt; setup.bat; README.md:-` | Regression guard; the copies agree today. Auditor F14. | tests/test_packaging.py::test_every_copy_of_the_version_agr… | 93cca89 |
| V-14 | low | `.gitignore:-` | Built Setup.exe showed as an untracked file. |  | ae36e9e |
| V-17 | low | `build_windows.bat:31` | Found by the independent review of this pass. | probe of the same lines from another folder | 823b604 |
| HO-FA-1@FB |  | `paperknife/tools/crop.py, paperknife/tools/headerfooter.py, paperknife/tools/password.py, paperknife/tools/pdftools.py, paperknife/tools/enhance.py:` | Uses job_queue.atomic_output (see HO-FC-2); checked on Windows with the input open: closing the doc in the in… | tests/test_fb.py::test_crop_can_overwrite_its_input | ebbdb57 |
| HO-FA-1@FE |  | `paperknife/tools/ocr.py, paperknife/tools/convert.py:` | FA handoff L1-27/L4-29/L1-28 (PREFS DPI and language) are the same change as L5-25/L3-32 | tests/test_fe.py::test_ocr_uses_preferences_language_and_dp… | d73e486 |
| HO-FA-2@FB |  | `paperknife/tools/enhance.py, paperknife/tools/batch.py, paperknife/tools/password.py, paperknife/tools/headerfooter.py, paperknife/tools/crop.py:` | import fitz -> import pymupdf as fitz in my files (pdftools.py no longer imports it at all) and in tests/test… | none: import rename | ebbdb57 |
| HO-FA-2@FE |  | `paperknife/tools/convert.py, paperknife/tools/ocr.py, paperknife/tools/metadata.py:` | FA handoff L1-08: final outputs written through job_queue.atomic_output (Image→PDF, PDF→Images, every PDF→Doc… | tests/test_fe.py::test_txt_to_pdf_cancel_stops_the_story_lo… | d73e486 |
| HO-FA-3@FB |  | `paperknife/tools/enhance.py:` | Compress and Watermark close the pre-opened input doc when run_job returns None (another job running). Status… | none: needs two concurrent jobs | ebbdb57 |
| HO-FA-3@FE |  | `paperknife/tools/convert.py, paperknife/tools/ocr.py, paperknife/tools/reader.py:` | FA handoff L4-60: 'import fitz' -> 'import pymupdf as fitz' (metadata.py no longer imports fitz at all: the i… | none: import rename | d73e486 |
| HO-FC-1@FB |  | `paperknife/tools/crop.py, paperknife/tools/headerfooter.py:` | Crop and Header/Footer use paperknife/pages.parse_ranges (via crop.selected_pages); PageRangeError shown with… | tests/test_fb.py::test_headerfooter_accepts_capitalised_end | ebbdb57 |
| HO-FC-2@FB |  | `paperknife/tools/crop.py, paperknife/tools/headerfooter.py, paperknife/tools/password.py, paperknife/tools/pdftools.py, paperknife/tools/enhance.py:` | All saves in crop, header/footer, password (protect + remove), PDF tools repair, compress, watermark and norm… | tests/test_fb.py::test_crop_can_overwrite_its_input | ebbdb57 |
| HO-FC-3@FB |  | `paperknife/tools/crop.py, paperknife/tools/headerfooter.py, paperknife/tools/pdftools.py, paperknife/tools/enhance.py, paperknife/tools/batch.py:` | Crop, header/footer, PDF tools, compress, watermark and normalise open the input with self._open_safe on the … | none: password prompt is a CTkInputDialog, not stubbed by t… | ebbdb57 |

## Needs your decision

| id | question |
|---|---|
| L1-04 | Should Ctrl+F stay on the sidebar tool search (MANUAL.md:225 documents it), or go to in-document find in Reader / Find & Replace with Ctrl+K left for the tool search? |
| L1-38 | Light-mode MUTED #7A7268 on SIDEBAR is 3.88:1 (below AA 4.5:1 for the 12px status bar and 9px headers): darken it to about #6A635A? |
| L2-33 | Owner question: should Remove Password refuse to strip restrictions from an owner-password-only PDF unless the owner password is entered (authenticate()==owner), and say 'this file was not encrypted' for plain inputs, i… |
| L2-36 | Owner question: Normalise redraws pages as XObjects and loses links, annotations, form fields and bookmarks - copy the TOC and warn, or rework it to resize in place (set_mediabox + content transform)? |
| L3-09 | Edited text is redrawn in a base-14 font (Helvetica when the PDF uses an embedded/subset font, so bold/italic is lost): reuse the embedded font via doc.extract_font where it is a full font, or keep Helvetica and tell th… |
| L3-17 | search_for misses a phrase hyphenated across a line break; probe: search_for('SECRET-ALPHA-42', flags=TEXT_DEHYPHENATE) on 'SECRET-AL-' / 'PHA-42' still returns []. Add a character-level hyphen-aware search (like Find &… |
| L3-50 | Move worker->UI calls (job_queue and every tool's app.after(0, ...)) to a queue.Queue drained by a main-thread after() poll, for non-threaded Tcl builds? Today python.org Tcl is threaded, and job_queue now survives a de… |
| L4-45 | Question: set upx=False for release builds (antivirus false positives, conflicts with signing, depends on UPX happening to be on PATH)? |
| L4-46 | Unmeasured: PyInstaller is not in the venv and the build is out of scope. README.md:13 says ~150 MB for the source install. Question: measure dist\PaperKnifePlusPC after a clean venv build and quote that number in both … |
| L5-04 | Owner question: restore v2's All / Odd / Even page selector (or a page-range entry like Crop) on the Watermark tool? Its subtitle says 'every page', so today's behaviour matches the label. |
| L5-08 | Owner question: re-add v2's input-size preview label ('Input: N KB · P pages') under the compression levels? |
| L5-11 | Bring back v2's per-span 'Revert span', 'Reset Page' and the blue/green edited-span legend alongside the (now working) Ctrl+Z undo? |
| L5-12 | Restore v2's Case-sensitive / Regex / Whole words checkboxes? (_find_matches now matches case exactly over the rawdict characters, so the three options would plug in there) |
| L5-14 | Rebind Ctrl+H to Find & Replace as in v2, or record its removal in the changelog? |
| L5-16 | Re-add a 'Clear All' button to the Merge list (v2 had one)? It is a new control, so the owner decides. |
| L5-17 | Merge subtitle says 'drag to reorder' but only Up/Down exist: reword to 'use ↑/↓ to reorder', or build drag-reorder? |
| L5-20 | Add an 'Open with...' choice on recent-file cards (v2 had one) or an 'Open in tool' action in the Reader? |
| L5-22 | Add Edit Text back to the Home quick actions? |
| L5-26 | Replace the free-text OCR language entry with an editable combo box filled from pytesseract.get_languages()? |
| L5-30 | Owner question: add a real PDF/A conversion through an external tool (Ghostscript -dPDFA=2 with an ICC OutputIntent, or ocrmypdf --output-type pdfa)? |
| L5-31 | Owner question: add linearisation through an external qpdf --linearize? |
| L5-50 | No page deletion anywhere (grep delete_page: 0 hits). Question: add Delete to Rotate & Reorder? |
| L5-51 | No signature tool. Question: add a signature-image stamp? |
| L5-52 | No grayscale operation. Question: add Grayscale (Document.recolor) to ENHANCE? |
| L5-53 | No compare tool. Question: add a visual/text Compare tool? |
| L5-54 | Add Insert blank page / Insert from PDF to Rotate & Reorder? |
| L5-55 | Add a Flatten (Document.bake) op to PDF Tools? |
| L5-56 | Add a form-filling tool (page.widgets())? |
| L5-57 | Add an Attachments tab (embfile_*)? |
| L5-58 | Add N-up / booklet imposition as a Normalise Pages mode? |
| L5-59 | Use PyMuPDF's pdfocr / get_textpage_ocr instead of the hOCR path, and add 'Make searchable' to Image to PDF? |
| L5-60 | Add Sanitise (scrub) and Subset fonts ops to PDF Tools? |
| RS-02 | Move the 15 tools' parse/save work off the Tk thread? Estimate ~2 days: the 11 single-shot tools are mechanical (~0.5 day); the 4 canvas editors need a busy state so the view cannot render or edit self._doc while a save… |
| RS-13 | Route the 9 hand-built file rows through app._file_row (adds drag-and-drop and the hint; widths 120-136 and heights 40-44 become 136x44) and add a ToolBase helper for the 8 Ctrl+O lambdas? |
| RS-14 | Replace the 15 hand-built primary buttons (heights 44/46) with app._big_btn (height 50, 16 pt bold), or add a compact card variant of _big_btn first? |
| V-18 | Signing: the PFX password reaches every signtool command line (/p); Uninstall.exe is written at install time and never signed (NSIS !uninstfinalize could); the loop re-signs Microsoft- and PSF-signed DLLs. Options: sign… |
| V-19 | Reproducible builds: no lock file and PyInstaller unpinned, so each build can pick up new major versions. Pillow>=10.0.0 is untested (no Python 3.14 wheel exists for it). Option: a requirements-lock.txt (pip freeze) tha… |
| V-20 | The desktop shortcut is created on every install, silent ones included. Keep, or make it an option on the finish page. Auditor F12. |
| V-21 | Install folder %LOCALAPPDATA%\PaperKnifePlusPC vs the per-user convention %LOCALAPPDATA%\Programs\PaperKnifePlusPC (upgrades now follow the registry either way). Auditor F15. |
| V-22 | Installer compression: measured LZMA 33.4 MB vs zlib 45.7 MB (-27%); silent install 8 s vs 5 s; makensis 42 s. Auditor F20. |

## Withdrawn

| id | reason |
|---|---|
| V-15 | Measured on the frozen exe: GetDpiAwarenessContextForProcess = PER_MONITOR_AWARE_V2. |

## Deferred

| id | reason |
|---|---|
| L5-21 | Thumbnails still render on the main thread. The mtime-keyed cache now makes repeat Home visits free; moving the first render off-thread needs placeholder cards and a CTkImage handoff through after(), which is more chang… |
| RS-05 | Home thumbnails/existence checks off the Tk thread need a worker plus placeholder cards; thumbnails are cached after the first visit and there is no correctness impact. Left for a performance pass. |
| V-23 | Revisit if an ARM64 build is wanted. UPX (auditor F9) is L4-45. |
| V-24 | Cosmetic. |
| V-25 | Belongs with L3-50 (queue-based UI updates), the owner's call. |

## Not reviewed or not verified

The verifying pass of 2026-10-02 (`verification-2026-10-02.md`) ran the real build,
silent install, upgrade and uninstall, real Tesseract 5.5, and the PyMuPDF 1.27.2 and
customtkinter floors. Still open:

- **Real drag and drop** from Explorer, the taskbar icon, and OCR from the installed
  app: an owner checklist in `verification-2026-10-02.md`. Tests prove tkdnd loads
  and drop targets register.
- **Installs from Explorer.** Installs made from the Claude app are redirected into
  its MSIX container, so a real-world install is the checklist's first step.
- **32-bit Windows** (the installer's refusal, V-10) and **signed builds** (V-18).
- **macOS / Linux.** Nothing was run there (see decision L4-07).
- **Visual layout.** No screenshots were compared; the app was launched and the
  views built headless in light and dark mode.

## Housekeeping (not code)

- The quarantined `PaperKnifePlusPC_v2.1(2)` folder carries a 444 MB one-file
  exe built from a global Python environment. Nothing was deleted.
- `PaperKnifePlusFixed.zip` ships a 120 MB `.venv`; `paperknife_clean.zip` has
  the same sources without it.

## Noted, no change

- `convert.py` parses user XML with `xml.etree.ElementTree`. The bundled expat is
  2.8.1; expat has limited entity expansion ("billion laughs") since 2.4.1, so no
  change was made. `defusedxml` would add a dependency for no current gain.
- No audit finding was withdrawn (V-15, from the verifying pass, was: measured).
  Each fixing lane was told to confirm a finding at its line before acting and to
  withdraw it otherwise; none did. The coordinator
  reproduced the headline defects independently, not all 322. Two hints were
  wrong and dropped: lane FB's note that merge/split kept their own range parsers
  (both call `pages.parse_ranges`) and ruff's F821 on `ImageTk` in edit_text.py
  (an annotation under `from __future__ import annotations`, never evaluated).

