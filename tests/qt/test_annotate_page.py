"""The Qt Annotate page: the document-workspace pilot."""
import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, wait_job


def _open(window, tmp_path, pages=2):
    src = make_pdf(tmp_path / "doc.pdf", pages=pages)
    assert window.open_tool("AnnotateTool", src)
    pump(0.1)
    page = window.current_page()
    assert page._doc is not None and len(page._doc) == pages
    return page, src


def _scene(page, x, y):
    """Scene position of the page point (x, y)."""
    r = page.view.page_to_scene(fitz.Rect(x, y, x, y))
    return r.x(), r.y()


def _drag(page, p0, p1):
    page._press(_scene(page, *p0))
    page._drag(_scene(page, *p1))
    page._mouse_up(_scene(page, *p1))


@pytest.mark.parametrize("kind,type_name", [
    ("highlight", "Highlight"), ("underline", "Underline"), ("strikeout", "StrikeOut"),
    ("rect", "Square"), ("line", "Line"), ("note", "Text"), ("freetext", "FreeText")])
def test_each_tool_adds_its_annotation_where_dragged(window, tmp_path, kind, type_name):
    page, _ = _open(window, tmp_path)
    page.set_kind(kind)
    _drag(page, (72, 90), (180, 110))
    pg = page._doc[0]                      # annotations need their page alive
    annots = list(pg.annots())
    assert len(annots) == 1 and annots[0].type[1] == type_name
    r = annots[0].rect
    if kind == "note":
        # A note is an icon anchored at the press point.
        assert (r.x0, r.y0) == (pytest.approx(72, abs=1), pytest.approx(90, abs=1))
        assert r.width < 30 and r.height < 30
        return
    # A highlight pads its rectangle around the text it marks (as in the CTk app);
    # a rect / line pads by half its border.
    tol = 6 if kind in ("highlight", "underline", "strikeout") else 2
    assert tuple(r) == pytest.approx((72, 90, 180, 110), abs=tol)
    flat = [c for v in (annots[0].vertices or []) for c in v]
    if kind in ("highlight", "underline", "strikeout"):
        # The marked quad is exactly the dragged rectangle.
        assert flat == pytest.approx([72, 90, 180, 90, 72, 110, 180, 110], abs=0.5)
    elif kind == "line":
        assert flat == pytest.approx([72, 90, 180, 110], abs=0.5)     # its two ends


def _shown(widget, page):
    """Shown on the page: alive (a rebuilt panel deletes its old rows) and visible."""
    from shiboken6 import isValid
    return isValid(widget) and widget.isVisibleTo(page)


def test_panel_follows_the_tool(window, tmp_path):
    page, _ = _open(window, tmp_path)
    page.set_kind("highlight")
    pump(0.05)                             # widgets added to a shown panel show next turn
    slider = page.opacity_slider
    assert slider.isVisibleTo(page)
    page.set_kind("note")
    pump(0.05)
    text_edit = page.text_edit
    assert text_edit.isVisibleTo(page)
    assert not _shown(slider, page), "the highlight's opacity row is still shown for a note"
    page.set_kind("highlight")
    pump(0.05)
    assert page.opacity_slider.isVisibleTo(page)
    assert not _shown(text_edit, page), "the note's text row is still shown for a highlight"


def test_click_selects_then_delete_removes(window, tmp_path):
    page, _ = _open(window, tmp_path)
    page.set_kind("rect")
    _drag(page, (100, 100), (200, 200))
    xy = _scene(page, 150, 150)
    page._press(xy)
    page._mouse_up(xy)
    assert page.sel_xref is not None
    page.delete()
    pg = page._doc[0]
    assert list(pg.annots()) == []


def test_undo_removes_the_last_annotation(window, tmp_path):
    page, _ = _open(window, tmp_path)
    page.set_kind("highlight")
    _drag(page, (72, 90), (180, 110))
    _drag(page, (72, 200), (180, 220))
    page.undo()
    pg = page._doc[0]
    left = list(pg.annots())
    assert len(left) == 1
    # The last one (y 200-220) went; the first (y 90-110) stays.
    assert left[0].rect.y0 == pytest.approx(90, abs=6) and left[0].rect.y1 < 150


def test_save_runs_as_a_job_and_writes_the_annotations(window, dialogs, tmp_path):
    page, _ = _open(window, tmp_path)
    page.set_kind("rect")
    _drag(page, (100, 100), (200, 200))
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    window.save_as()
    wait_job(window)
    with fitz.open(out) as d:
        pg = d[0]
        assert [a.type[1] for a in pg.annots()] == ["Square"]


def test_save_over_the_open_file(window, dialogs, tmp_path):
    page, src = _open(window, tmp_path)
    page.set_kind("rect")
    _drag(page, (100, 100), (200, 200))
    before = open(src, "rb").read()
    page.save()                         # the window's Save: over the file, no dialog
    wait_job(window)
    assert open(src, "rb").read().startswith(before)     # a note only adds: appended
    with fitz.open(src) as d:
        pg = d[0]
        assert len(list(pg.annots())) == 1
    assert page._doc is not None and not page._doc.is_closed


def test_drop_takes_pdfs_only(window, tmp_path):
    page, _ = _open(window, tmp_path)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    second = make_pdf(tmp_path / "second.pdf", pages=4)
    assert page.accept_drop(second) is True
    assert len(page._doc) == 4


def test_page_strip_moves_between_pages(window, tmp_path):
    page, _ = _open(window, tmp_path, pages=3)
    page.go(1)
    assert page._pg == 1 and page.page_label.text() == "2 / 3"
    page.go(5)
    assert page._pg == 1


def test_context_panel_collapses_below_its_minimum(window, tmp_path):
    page, _ = _open(window, tmp_path)
    total = sum(page.split.sizes())
    # Drag the handle to 100 px from the right edge, past the 220 px minimum.
    page.split.moveSplitter(total - 100, 1)
    pump(0.4)
    assert page.context_width() == 0 and page.reopen_btn.isVisibleTo(page)
    page.show_context(True)
    pump(0.4)
    assert page.context_width() > 0


def test_leaving_the_tool_keeps_the_document(window, tmp_path):
    page, _ = _open(window, tmp_path)
    doc = page._doc
    window.show_page("home")
    assert not doc.is_closed and window.document.doc is doc


@pytest.mark.parametrize("kind", ["highlight", "underline", "strikeout"])
def test_a_drag_along_a_line_marks_that_line(window, tmp_path, kind):
    """Dragging straight along a line spans no height: PyMuPDF refused it as "bad
    quads entry" and the status showed an error (the live walk, 2026-10-22).  The
    mark keeps the drag's width and takes the line's height; along empty paper a
    drag adds nothing and says why."""
    page, _ = _open(window, tmp_path)
    page.set_kind(kind)
    pg = page._doc[0]
    word = pg.search_for("Page 1")[0]
    y = (word.y0 + word.y1) / 2
    _drag(page, (60, y), (140, y))
    annots = list(pg.annots())
    assert len(annots) == 1, window.status_text()
    flat = [c for v in annots[0].vertices for c in v]
    xs, ys = flat[0::2], flat[1::2]
    assert (min(xs), max(xs)) == (pytest.approx(60, abs=0.5), pytest.approx(140, abs=0.5))
    assert min(ys) == pytest.approx(word.y0, abs=1) and max(ys) == pytest.approx(word.y1, abs=1)
    assert "error" not in window.status_text().lower()
    _drag(page, (300, 600), (400, 600))                    # empty paper: nothing added
    assert len(list(pg.annots())) == 1
    assert "No text under the drag" in window.status_text()
