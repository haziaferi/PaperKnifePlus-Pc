"""The editors' page strip (owner, 2026-10-18): thumbnails left of the page in
Edit Text, Find & Replace, Annotate and Redact; click to go, Ctrl / Shift to
select several, drag to move; the rail's Pages tool turns and deletes the
selection; one Undo steps back through edits and page changes in order."""
import pymupdf as fitz
import pytest
from PySide6.QtCore import QModelIndex

from qt_harness import make_pdf, pump, wait_job

EDITORS = ["EditTextTool", "FindReplaceTool", "AnnotateTool", "RedactTool"]


def _open(window, tmp_path, tool="AnnotateTool", pages=4):
    src = make_pdf(tmp_path / "doc.pdf", pages=pages)
    assert window.open_tool(tool, src)
    page = window.current_page()
    _drawn(page)
    assert page._doc is not None and len(page._doc) == pages
    return page, src


def _drawn(page):
    while page.thumbs.rendering():
        pump(0.02)
    pump(0.05)


def _texts(doc):
    return [doc[i].get_text().strip() for i in range(len(doc))]


def _select(page, *rows):
    page.thumbs.clearSelection()
    for r in rows:
        page.thumbs.item(r).setSelected(True)


def _rail(page, key):
    for i in range(page.rail.count()):
        w = page.rail.itemAt(i).widget()
        if w is not None and getattr(w, "pk_key", None) == key:
            return w
    raise AssertionError(f"no rail button {key!r}")


@pytest.mark.parametrize("tool", EDITORS)
def test_each_editor_shows_a_thumbnail_per_page_and_a_pages_tool(window, tmp_path, tool):
    page, _ = _open(window, tmp_path, tool)
    assert page.strip_shown()
    assert page.thumbs.count() == 4
    assert [page.thumbs.item(i).text() for i in range(4)] == ["p.1", "p.2", "p.3", "p.4"]
    assert all(not page.thumbs.item(i).icon().isNull() for i in range(4))
    _rail(page, "pages")


def test_the_reader_has_no_strip(window, tmp_path):
    src = make_pdf(tmp_path / "doc.pdf", pages=2)
    assert window.open_tool("ReaderTool", src)
    assert window.current_page().thumbs is None


def test_no_document_no_strip(window, tmp_path):
    window.open_tool("AnnotateTool")
    page = window.current_page()
    assert page.strip_box.isHidden() and not page.strip_reopen_btn.isVisible()


def test_a_click_goes_to_the_page_and_paging_moves_the_strip(window, tmp_path):
    page, _ = _open(window, tmp_path)
    page.thumbs.setCurrentRow(2)
    assert page._pg == 2 and page.page_label.text() == "3 / 4"
    page.go(-1)
    assert page.thumbs.currentRow() == 1
    assert page.thumbs.selected_rows() == [1]       # the page gone to is the selection


def test_ctrl_click_keeps_a_selection_of_several(window, tmp_path):
    page, _ = _open(window, tmp_path)
    _select(page, 0, 2)
    page._strip_clicked(page.thumbs.item(2))        # the click that made 2 current
    assert page._pg == 2 and page.thumbs.selected_rows() == [0, 2]


def test_pages_panel_comes_and_goes_with_the_rail(window, tmp_path):
    page, _ = _open(window, tmp_path)
    _rail(page, "pages").click()
    assert page._pages_on and page._pages_box.isVisibleTo(page)
    assert not page._panel_tools.isVisibleTo(page)
    assert _rail(page, "pages").isChecked() and not _rail(page, "highlight").isChecked()
    page.go(1)                                      # a tool rebuilds its panel on a new page
    assert page._pages_box.isVisibleTo(page) and _rail(page, "pages").isChecked()
    _rail(page, "rect").click()
    assert not page._pages_on and page._panel_tools.isVisibleTo(page)
    assert page.kind == "rect" and _rail(page, "rect").isChecked()


def test_find_and_replace_gets_its_own_rail_tool_back_from_pages(window, tmp_path):
    page, _ = _open(window, tmp_path, "FindReplaceTool")
    assert _rail(page, "find").isChecked()
    _rail(page, "pages").click()
    assert page._pages_on
    _rail(page, "find").click()
    assert not page._pages_on and page.find_edit.isVisibleTo(page)
    assert _rail(page, "find").isChecked()


def test_pages_panel_wording(window, tmp_path):
    from paperknife.qt.pages import PAGES_DESC
    page, _ = _open(window, tmp_path)
    page.show_pages_panel(True)
    assert PAGES_DESC == "Select pages in the strip · drag them to move"
    assert [b.text() for b in (page.rotate_left_btn, page.rotate_right_btn,
                               page.delete_pages_btn)] == ["Rotate left", "Rotate right", "Delete"]


def test_rotate_turns_the_selection_and_undo_turns_it_back(window, tmp_path):
    page, _ = _open(window, tmp_path)
    page.show_pages_panel(True)
    _select(page, 1, 3)
    page.rotate_right_btn.click()
    assert [page._doc[i].rotation for i in range(4)] == [0, 90, 0, 90]
    assert page.thumbs.selected_rows() == [1, 3] and page.is_dirty()
    page.rotate_left_btn.click()
    page.rotate_left_btn.click()
    assert [page._doc[i].rotation for i in range(4)] == [0, 270, 0, 270]
    for _ in range(3):
        page.undo()
    assert [page._doc[i].rotation for i in range(4)] == [0, 0, 0, 0]


def test_delete_asks_names_the_pages_and_undo_brings_them_back(window, tmp_path, dialogs):
    page, _ = _open(window, tmp_path)
    page.show_pages_panel(True)
    _select(page, 1, 2)
    dialogs.asks.append(True)
    page.delete_pages_btn.click()
    assert dialogs.msgs[-1] == ("ask_yes_no", "Delete pages",
                                "Delete pages 2 and 3? Undo brings them back until you save.")
    assert _texts(page._doc) == ["Page 1", "Page 4"]
    assert page.thumbs.count() == 2
    page.undo()
    assert _texts(page._doc) == ["Page 1", "Page 2", "Page 3", "Page 4"]
    assert page.thumbs.count() == 4


def test_delete_said_no_changes_nothing(window, tmp_path, dialogs):
    page, _ = _open(window, tmp_path)
    page.show_pages_panel(True)
    _select(page, 0)
    dialogs.asks.append(False)
    page.delete_pages_btn.click()
    assert len(page._doc) == 4 and not page.is_dirty()


def test_delete_is_off_with_every_page_selected(window, tmp_path):
    from paperknife.qt.pages import KEEP_ONE
    page, _ = _open(window, tmp_path)
    page.show_pages_panel(True)
    page.thumbs.selectAll()
    assert not page.delete_pages_btn.isEnabled() and page.pages_hint.text() == KEEP_ONE
    assert page.rotate_left_btn.isEnabled()
    _select(page, 0)
    assert page.delete_pages_btn.isEnabled() and page.pages_hint.text() == ""


def test_deleting_the_page_shown_shows_the_next(window, tmp_path, dialogs):
    page, _ = _open(window, tmp_path)
    page.thumbs.setCurrentRow(1)
    _select(page, 1)
    dialogs.asks.append(True)
    page.delete_pages()
    assert page._pg == 1 and page._doc[1].get_text().strip() == "Page 3"


def test_a_drag_moves_the_pages_and_undo_puts_them_back(window, tmp_path):
    page, _ = _open(window, tmp_path)
    m = page.thumbs.model()
    assert m.moveRow(QModelIndex(), 0, QModelIndex(), 3)      # p.1 dragged after p.3
    pump(0.1)
    assert _texts(page._doc) == ["Page 2", "Page 3", "Page 1", "Page 4"]
    assert [page.thumbs.item(i).text() for i in range(4)] == ["p.1", "p.2", "p.3", "p.4"]
    page.undo()
    assert _texts(page._doc) == ["Page 1", "Page 2", "Page 3", "Page 4"]


def test_a_move_keeps_the_bookmarks_with_their_pages(window, tmp_path):
    src = make_pdf(tmp_path / "toc.pdf", pages=3)
    d = fitz.open(src)
    d.set_toc([[1, "Third", 3]])
    d.saveIncr()
    d.close()
    assert window.open_tool("AnnotateTool", src)
    page = window.current_page()
    _drawn(page)
    page._strip_moved([2, 0, 1])
    assert page._doc.get_toc() == [[1, "Third", 1]]


def test_one_undo_steps_back_through_edits_and_page_changes(window, tmp_path):
    page, _ = _open(window, tmp_path)
    page.set_kind("rect")
    page._add_at(*_box(page, 0), click=False)
    _select(page, 0)
    page.rotate_pages(90)
    page._add_at(*_box(page, 0), click=False)
    assert len(list(page._doc[0].annots())) == 2 and page._doc[0].rotation == 90
    page.undo()
    assert len(list(page._doc[0].annots())) == 1 and page._doc[0].rotation == 90
    page.undo()
    assert len(list(page._doc[0].annots())) == 1 and page._doc[0].rotation == 0
    page.undo()
    assert len(list(page._doc[0].annots())) == 0


def _box(page, pg):
    page._pg = pg
    page.show_current()
    r0 = page.view.page_to_scene(fitz.Rect(72, 90, 72, 90))
    r1 = page.view.page_to_scene(fitz.Rect(150, 130, 150, 130))
    return (r0.x(), r0.y()), (r1.x(), r1.y())


def test_annotate_writes_the_file_whole_after_a_delete(window, tmp_path, dialogs):
    page, _ = _open(window, tmp_path)
    assert window.document.adds_only
    _select(page, 3)
    dialogs.asks.append(True)
    page.delete_pages()
    assert not window.document.adds_only


def test_the_new_order_is_saved(window, tmp_path, dialogs):
    page, _ = _open(window, tmp_path)
    page._strip_moved([3, 2, 1, 0])
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    window.save_as()
    wait_job(window)
    with fitz.open(out) as d:
        assert _texts(d) == ["Page 4", "Page 3", "Page 2", "Page 1"]


def test_redact_boxes_follow_their_pages(window, tmp_path, dialogs):
    page, _ = _open(window, tmp_path, "RedactTool")
    page._add_box(*_box(page, 2), click=False)
    assert [b[0] for b in page._pending] == [2]
    _select(page, 0)
    dialogs.asks.append(True)
    page.delete_pages()
    assert [b[0] for b in page._pending] == [1]
    assert page.pending_label.text() == "1 box pending"
    page.undo()
    assert [b[0] for b in page._pending] == [2] and len(page._doc) == 4


def test_redact_a_box_drawn_after_a_page_change_comes_off_first(window, tmp_path):
    page, _ = _open(window, tmp_path, "RedactTool")
    page._strip_moved([1, 0, 2, 3])
    page._add_box(*_box(page, 0), click=False)
    page.undo()
    assert page._pending == [] and _texts(page._doc)[0] == "Page 2"
    page.undo()
    assert _texts(page._doc)[0] == "Page 1"


def test_redact_s_page_changes_are_the_document_s_and_save_writes_them(window, tmp_path,
                                                                       dialogs):
    # One document per window (owner, 2026-10-23): Redact's page strip edits the
    # document; Save writes it, no question about boxes.
    page, src = _open(window, tmp_path, "RedactTool")
    _select(page, 1)
    dialogs.asks.append(True)
    page.delete_pages()
    page.save()
    wait_job(window)
    with fitz.open(src) as d:
        assert _texts(d) == ["Page 1", "Page 3", "Page 4"]
    assert not page.is_dirty()


def test_redact_without_boxes_or_page_changes_still_says_so(window, tmp_path, dialogs):
    page, _ = _open(window, tmp_path, "RedactTool")
    page.apply_redactions()
    assert dialogs.msgs[-1] == ("info", "Apply", "No redaction boxes drawn yet.")


def test_find_and_replace_hits_follow_their_pages(window, tmp_path, dialogs):
    page, _ = _open(window, tmp_path, "FindReplaceTool")
    page.find_edit.setText("Page")
    page.find_all()
    wait_job(window)
    assert [h[0] for h in page._hits] == [0, 1, 2, 3]
    _select(page, 1)
    dialogs.asks.append(True)
    page.delete_pages()
    assert [h[0] for h in page._hits] == [0, 1, 2]
    _select(page, 0)
    page.rotate_pages(90)
    assert [h[0] for h in page._hits] == [1, 2]     # a turned page's hits go
    page.undo()
    page.undo()
    assert [h[0] for h in page._hits] == [0, 1, 2, 3]


def test_edit_text_undo_reaches_a_page_change(window, tmp_path, dialogs):
    page, _ = _open(window, tmp_path, "EditTextTool")
    _select(page, 0)
    dialogs.asks.append(True)
    page.delete_pages()
    assert len(page._doc) == 3
    page.undo()
    assert len(page._doc) == 4 and page._undo_stack == []


def test_strip_hides_and_is_remembered(window, tmp_path, qapp, dialogs):
    from paperknife.prefs import PREFS
    from paperknife.qt.shell import MainWindow
    page, src = _open(window, tmp_path)
    page.show_strip(False)
    pump(0.4)
    assert page.outer.sizes()[0] == 0 and page.strip_reopen_btn.isVisible()
    assert PREFS.qt_page_strip is False
    w2 = MainWindow()
    w2.show()
    try:
        assert w2.open_tool("EditTextTool", src)
        p2 = w2.current_page()
        pump(0.1)
        assert p2.outer.sizes()[0] == 0 and p2.strip_reopen_btn.isVisible()
        p2.show_strip(True)
        pump(0.4)
        assert p2.outer.sizes()[0] > 0 and PREFS.qt_page_strip is True
    finally:
        from conftest import close_test_window
        close_test_window(w2)


def test_double_click_on_the_strip_edge_toggles_it(window, tmp_path):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    page, _ = _open(window, tmp_path)
    ev = QMouseEvent(QEvent.MouseButtonDblClick, QPointF(2, 2), QPointF(2, 2),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    assert page.eventFilter(page._strip_handle, ev)
    pump(0.4)
    assert page.outer.sizes()[0] == 0
    assert page.context_shown()                     # the panel is not the one toggled


def test_no_thumbnail_is_drawn_while_a_job_has_the_document(window, tmp_path, monkeypatch):
    page, _ = _open(window, tmp_path)

    class Busy:
        is_running = True
        _thread = None
    monkeypatch.setattr(window, "_current_job", Busy())
    page.strip_refresh()
    pump(0.15)
    assert page.thumbs.rendering()
    monkeypatch.setattr(window, "_current_job", None)
    _drawn(page)
    assert not page.thumbs.rendering()
