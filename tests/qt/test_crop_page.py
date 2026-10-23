"""The Qt Crop / Trim page: cut margins off the crop box of selected pages."""
import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, save_as, wait_job


def _page(window):
    assert window.open_tool("CropTool")
    pump(0.05)
    return window.current_page()


def _crop(window, dialogs, src, out, rng="", reset=False, **margins):
    page = _page(window)
    page.file.set_path(str(src))
    for k, edit in page.margins.items():      # the page keeps its fields between runs
        edit.setText(str(margins.get(k, 0)))
    page.page_range.setText(rng)
    page.reset.setChecked(reset)
    page.run()
    wait_job(window)
    save_as(window, dialogs, out)
    return page


def _sizes(path):
    with fitz.open(path) as doc:
        return [(round(p.rect.width), round(p.rect.height)) for p in doc]


def test_the_page_builds_with_its_controls(window):
    page = _page(window)
    assert type(page).__name__ == "CropPage"
    assert page.title_label.text() == "Crop / Trim"
    assert {k: e.text() for k, e in page.margins.items()} == {
        "top": "0", "left": "0", "right": "0", "bottom": "0"}
    assert not page.reset.isChecked() and page.page_range.text() == ""


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Crop", "Select a PDF first.")


@pytest.mark.parametrize("margins, words", [
    ({}, "All margins are 0 — nothing to crop."),
    ({"top": "abc"}, "Enter numeric values for all margins."),
    ({"top": -10}, "Margins cannot be negative."),
])
def test_unusable_margins_are_refused_up_front(window, dialogs, tmp_path, margins, words,
                                               monkeypatch):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    _crop(window, dialogs, src, out, **margins)
    assert not dialogs.errors(), dialogs.errors()
    assert dialogs.msgs[-1] == ("warning", "Crop", words)
    assert window._current_job is None and not out.exists()


@pytest.mark.parametrize("edge, size, shift", [
    ("top", (595, 792), (0, -50)), ("bottom", (595, 792), (0, 0)),
    ("left", (545, 842), (-50, 0)), ("right", (545, 842), (0, 0)),
])
def test_each_margin_cuts_its_own_edge(window, dialogs, tmp_path, edge, size, shift):
    src = make_pdf(tmp_path / "in.pdf", pages=2)          # A4: 595 x 842 pt
    out = tmp_path / "out.pdf"
    _crop(window, dialogs, src, out, **{edge: 50})
    assert not dialogs.errors(), dialogs.errors()
    assert _sizes(out) == [size, size]
    with fitz.open(src) as a, fitz.open(out) as b:
        wa, wb = a[0].get_text("words")[0], b[0].get_text("words")[0]
    assert wb[4] == "Page"
    assert (round(wb[0] - wa[0]), round(wb[1] - wa[1])) == shift
    assert not [m for m in dialogs.msgs if m[0] == "info"]
    assert window.applied_status == "✓  Cropped 2 page(s) · Save writes it to the file"


def test_crop_top_cuts_the_visible_top_of_a_rotated_page(window, dialogs, tmp_path):
    doc = fitz.open()
    doc.new_page().set_rotation(90)          # seen as 842 x 595
    doc.save(tmp_path / "in.pdf")
    doc.close()
    out = tmp_path / "out.pdf"
    _crop(window, dialogs, tmp_path / "in.pdf", out, top=100)
    assert not dialogs.errors(), dialogs.errors()
    assert _sizes(out) == [(842, 495)]


def test_the_page_range_crops_only_the_pages_it_names(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=4)
    out = tmp_path / "out.pdf"
    _crop(window, dialogs, src, out, rng="2, 4-end", top=50)
    assert [h for _, h in _sizes(out)] == [842, 792, 842, 792]
    assert window.applied_status == "✓  Cropped 2 page(s) · Save writes it to the file"


def test_crop_overlapping_ranges_crop_once(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    _crop(window, dialogs, src, out, rng="1-3, 2", top=50)
    assert [h for _, h in _sizes(out)] == [792, 792, 792]


def test_a_bad_page_range_is_an_error_and_closes_the_document(window, dialogs, tmp_path,
                                                              monkeypatch):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    page = _crop(window, dialogs, src, out, rng="9", top=50)
    assert dialogs.errors()[-1][1] == "Crop" and "page 9 does not exist" in dialogs.errors()[-1][2]
    assert window._current_job is None and not out.exists()
    assert page._doc is not None                     # the page still shows the document


def test_reset_undoes_previous_crops_first(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    first = tmp_path / "first.pdf"
    _crop(window, dialogs, src, first, top=100)
    kept, reset = tmp_path / "kept.pdf", tmp_path / "reset.pdf"
    _crop(window, dialogs, first, kept, bottom=50)
    _crop(window, dialogs, first, reset, bottom=50, reset=True)
    assert _sizes(kept) == [(595, 692)]
    assert _sizes(reset) == [(595, 792)]


def test_a_page_smaller_than_its_margins_is_skipped_with_a_warning(window, dialogs, tmp_path):
    doc = fitz.open()
    doc.new_page()
    doc.new_page(width=100, height=100)
    doc.save(tmp_path / "in.pdf")
    doc.close()
    out = tmp_path / "out.pdf"
    _crop(window, dialogs, tmp_path / "in.pdf", out, top=60, bottom=60)
    assert _sizes(out) == [(595, 722), (100, 100)]
    assert window.applied_status == (
        "⚠  Cropped 1 page(s) · 1 skipped (margins larger than the page) · Save writes it to "
        "the file")


def test_margins_larger_than_every_page_are_refused_without_saving(window, dialogs, tmp_path):
    # R45-3: nothing was cropped, an identical copy was written and the box
    # said "Cropped PDF saved".
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(tmp_path / "in.pdf")
    doc.close()
    out = tmp_path / "out.pdf"
    page = _page(window)
    page.file.set_path(str(tmp_path / "in.pdf"))
    for edit in page.margins.values():
        edit.setText("150")
    page.page_range.setText("")
    page.reset.setChecked(False)
    page.run()
    wait_job(window)
    save_as(window, dialogs, out)
    assert not out.exists() and not window.document.dirty      # nothing changed
    assert not [m for m in dialogs.msgs if m[0] == "info"]
    assert dialogs.warnings() == [
        ("warning", "Crop", "No page was cropped: the margins are larger than every "
                            "selected page.")]


def test_crop_can_overwrite_its_input(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    _crop(window, dialogs, src, src, top=50)
    assert not dialogs.errors(), dialogs.errors()
    assert [h for _, h in _sizes(src)] == [792, 792, 792]


def test_a_dropped_pdf_fills_the_file_card_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


def test_crop_asks_no_file_name_and_undo_takes_it_back(window, dialogs, tmp_path):
    # Applied to the document (owner's sort, 2026-10-23).
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.margins["top"].setText("50")
    held = page._doc
    page.run()                     # no file name asked (the harness would hand it nothing)
    wait_job(window)
    assert round(page._doc[0].rect.height) == 792 and window.document.dirty
    assert held.is_closed          # the content was replaced: the old one is let go
    assert window.undo() and round(page._doc[0].rect.height) == 842
    assert not window.document.dirty


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.margins["top"].setText("50")
    page.run()
    window.show_page("CompressTool")            # refused while the job holds the view
    wait_job(window)
    assert window.show_page("CompressTool")
    # left: the window keeps the one document, cropped (2026-10-23)
    assert [round(p.rect.height) for p in window.document.doc] == [792, 792, 792]
    assert not window.document.doc.is_closed


# ── the pages on screen (owner, 2026-10-17) ─────────────────────────────────
def _open(window, tmp_path, pages=4):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=pages))
    pump(0.1)
    return page


def test_every_page_is_selected_and_the_field_reads_all(window, tmp_path):
    page = _open(window, tmp_path)
    assert page.order() == [0, 1, 2, 3] and page.pages() == [0, 1, 2, 3]
    assert page.page_range.text() == "all" and not page.all_btn.isEnabled()


def test_the_selection_and_the_range_field_stay_in_step(window, dialogs, tmp_path):
    page = _open(window, tmp_path, pages=5)
    page.grid.clearSelection()
    for r in (0, 2, 3):
        page.grid.item(r).setSelected(True)
    assert page.page_range.text() == "1, 3-4"
    page.page_range.setText("2, 5")
    assert page.pages() == [1, 4]
    page.page_range.setText("2-end")
    assert page.pages() == [1, 2, 3, 4] and page.page_range.text() == "2-end"   # kept as typed
    page.page_range.setText("2, 5")
    page.page_range.setText("9")                      # not a page: the selection stays
    assert page.pages() == [1, 4]
    page.select_all_pages()
    assert page.page_range.text() == "all"
    out = tmp_path / "out.pdf"
    page.page_range.setText("2, 5")
    page.margins["top"].setText("50")
    page.run()
    wait_job(window)
    save_as(window, dialogs, out)
    assert [h for _, h in _sizes(out)] == [842, 792, 842, 842, 792]


def test_no_page_selected_turns_crop_off_and_says_why(window, tmp_path):
    page = _open(window, tmp_path)
    crop = next(b for b in page._buttons if getattr(b, "pk_primary", False))
    page.grid.clearSelection()
    assert not crop.isEnabled() and page.hint_label.text() == "Select at least one page."
    page.select_all_pages()
    assert crop.isEnabled()
