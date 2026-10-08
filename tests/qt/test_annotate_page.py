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
    # A highlight pads its rectangle around the text it marks (as in the CTk app).
    tol = 6 if kind in ("highlight", "underline", "strikeout") else 2
    assert kind == "note" or r.x0 == pytest.approx(72, abs=tol)


def test_panel_follows_the_tool(window, tmp_path):
    page, _ = _open(window, tmp_path)
    page.set_kind("highlight")
    pump(0.05)                             # widgets added to a shown panel show next turn
    assert page.opacity_slider.isVisibleTo(page)
    page.set_kind("note")
    pump(0.05)
    assert page.text_edit.isVisibleTo(page)


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
    assert len(list(pg.annots())) == 1


def test_save_runs_as_a_job_and_writes_the_annotations(window, dialogs, tmp_path):
    page, _ = _open(window, tmp_path)
    page.set_kind("rect")
    _drag(page, (100, 100), (200, 200))
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.save()
    wait_job(window)
    with fitz.open(out) as d:
        pg = d[0]
        assert [a.type[1] for a in pg.annots()] == ["Square"]


def test_save_over_the_open_file(window, dialogs, tmp_path):
    page, src = _open(window, tmp_path)
    page.set_kind("rect")
    _drag(page, (100, 100), (200, 200))
    dialogs.save(src)
    page.save()
    wait_job(window)
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


def test_leaving_the_tool_closes_the_document(window, tmp_path):
    page, _ = _open(window, tmp_path)
    doc = page._doc
    window.show_page("home")
    assert doc.is_closed and page._doc is None
