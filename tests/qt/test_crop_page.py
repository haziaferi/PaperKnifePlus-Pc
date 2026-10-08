"""The Qt Crop / Trim page: cut margins off the crop box of chosen pages."""
import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, wait_job


def _page(window):
    assert window.open_tool("CropTool")
    pump(0.05)
    return window.current_page()


def _spy_open(window):
    opened = []
    real = window.open_pdf_safe

    def spy(path):
        doc = real(path)
        opened.append(doc)
        return doc
    window.open_pdf_safe = spy
    return opened


def _crop(window, dialogs, src, out, rng="", reset=False, **margins):
    page = _page(window)
    page.file.set_path(str(src))
    for k, edit in page.margins.items():      # the page keeps its fields between runs
        edit.setText(str(margins.get(k, 0)))
    page.page_range.setText(rng)
    page.reset.setChecked(reset)
    dialogs.save(out)
    page.run()
    wait_job(window)
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
def test_unusable_margins_are_refused_up_front(window, dialogs, tmp_path, margins, words):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    opened = _spy_open(window)
    _crop(window, dialogs, src, out, **margins)
    assert not dialogs.errors(), dialogs.errors()
    assert dialogs.msgs[-1] == ("warning", "Crop", words)
    assert opened == [] and not out.exists()


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
    assert dialogs.msgs[-1] == ("info", "Done", f"Cropped PDF saved:\n{out}")
    assert window.status_text() == "✓  Cropped 2 page(s) → out.pdf"
    assert window.status_role == "success"


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
    assert window.status_text() == "✓  Cropped 2 page(s) → out.pdf"


def test_crop_overlapping_ranges_crop_once(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    _crop(window, dialogs, src, out, rng="1-3, 2", top=50)
    assert [h for _, h in _sizes(out)] == [792, 792, 792]


def test_a_bad_page_range_is_an_error_and_closes_the_document(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    opened = _spy_open(window)
    _crop(window, dialogs, src, out, rng="9", top=50)
    assert dialogs.errors()[-1][1] == "Crop" and "page 9 does not exist" in dialogs.errors()[-1][2]
    assert opened and opened[0].is_closed and not out.exists()


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
    assert window.status_text() == (
        "✓  Cropped 1 page(s) · 1 skipped (margins larger than the page) → out.pdf")
    assert window.status_role == "warning"


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


def test_cancelling_the_save_dialog_closes_the_document(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.margins["top"].setText("50")
    opened = _spy_open(window)
    page.run()                     # no save path queued: the dialog returns ""
    assert opened and opened[0].is_closed
    assert window._current_job is None


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.margins["top"].setText("50")
    opened = _spy_open(window)
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.run()
    window.show_page("CompressTool")
    wait_job(window)
    assert opened and opened[0].is_closed
    assert [h for _, h in _sizes(out)] == [792, 792, 792]
