"""The two layouts for opening a file (env PK_DOCUI=nav|bar, default nav;
phase9/docui-brief.md section 2): every page builds in both, light and
dark; the open control is where the owner put it (nav: the slot directly
under the search box, full pane width, 40 px; bar: a row directly under the
subtitle at the page's left margin); the collapsed navigation shows a 40x40
file icon button with the same list; pages show no FileCard; a page with no
document shows the empty-state target."""
import pytest
from PySide6.QtCore import QPoint

from qt_harness import make_pdf, pump, wait_job

NO_FOLLOW = {"MergeTool", "Img2PdfTool", "BatchTool", "SettingsTool", "Doc2PdfTool"}


@pytest.fixture
def make_window(qapp, dialogs, monkeypatch):
    """make_window(layout): a MainWindow built with PK_DOCUI=layout (the
    conftest window is built before a test can set the variable)."""
    made = []

    def make(layout):
        from paperknife.qt.shell import MainWindow
        monkeypatch.setenv("PK_DOCUI", layout)
        w = MainWindow()
        w.move(0, 0)
        w._pointer = lambda: w.mapToGlobal(QPoint(w.width() // 2, w.height() // 2))
        w.show()
        pump(0.05)
        made.append(w)
        return w
    yield make
    for w in made:
        if w._current_job is not None and w._current_job.is_running:
            w._current_job.cancel()
            wait_job(w)
        w._close_ok = True
        w._alive = False
        w._edge.stop()
        w.close()
        w.deleteLater()
    pump(0.02)


def _pages():
    from paperknife.qt.pages import QT_PAGES
    return list(QT_PAGES)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("layout", ["nav", "bar"])
def test_every_page_builds_in_both_layouts(make_window, tmp_path, layout, dark):
    from paperknife.qt import theme
    from paperknife.qt.pages import FileCard
    theme.apply_appearance("dark" if dark else "light")
    try:
        win = make_window(layout)
        src = make_pdf(tmp_path / "a.pdf")
        for name in _pages():
            assert win.open_tool(name), name
            pump(0.02)
            page = win.current_page()
            assert page.isVisible(), name
            if name in NO_FOLLOW:
                continue
            assert not [c for c in page.findChildren(FileCard) if c.isVisibleTo(page)], name
            assert page.drop_target.isVisibleTo(page), name        # no document yet
        win.open_document(src)
        for name in _pages():
            assert win.open_tool(name), name
            pump(0.02)
            page = win.current_page()
            if name in NO_FOLLOW:
                continue
            assert not [c for c in page.findChildren(FileCard) if c.isVisibleTo(page)], name
            assert not page.drop_target.isVisibleTo(page), name

            sub = page.subtitle_label.text()
            if layout == "nav":
                assert sub.endswith("a.pdf"), (name, sub)
                assert page.doc_bar is None
            else:
                assert page.doc_bar.isVisibleTo(page), name
                assert page.doc_bar.chip.name_label.text() == "a.pdf", name
    finally:
        theme.apply_appearance("light")


def test_nav_slot_sits_directly_under_the_search_box(make_window, tmp_path):
    from paperknife.qt.docui import NO_DOCUMENT, OPEN_TEXT
    win = make_window("nav")
    panel = win.navigationInterface.panel
    top = panel.topLayout
    i = top.indexOf(win.search)
    assert top.itemAt(i + 1).widget() is win.doc_slot
    s, d = win.search.geometry(), win.doc_slot.geometry()
    assert d.left() == s.left() and d.width() == s.width()          # full pane width
    assert 0 <= d.top() - s.bottom() - 1 <= top.spacing()
    assert d.height() == 40
    assert win.doc_slot.name_label.text() == NO_DOCUMENT
    assert win.doc_slot.open_control.text() == OPEN_TEXT
    assert not win.doc_slot.clear_btn.isVisibleTo(win.doc_slot)
    src = make_pdf(tmp_path / "report.pdf")
    win.open_document(src)
    assert win.doc_slot.name_label.text() == "report.pdf"
    assert win.doc_slot.name_label.toolTip() == src
    assert win.doc_slot.icon.isVisibleTo(win.doc_slot)
    assert win.doc_slot.clear_btn.isVisibleTo(win.doc_slot)
    win.doc_slot.clear_btn.click()
    assert win.current_document is None


def test_nav_slot_collapses_to_a_file_icon_button_with_the_same_list(make_window, tmp_path):
    from paperknife.qt.docui import BROWSE_TEXT
    from paperknife.recent import RECENT
    win = make_window("nav")
    src = make_pdf(tmp_path / "report.pdf")
    RECENT.push(src, 3)
    win.open_document(src)
    win.toggle_nav()
    pump(0.35)
    slot = win.doc_slot
    assert slot.isCompacted and (slot.width(), slot.height()) == (40, 40)
    assert slot.compact_btn.isVisibleTo(slot) and not slot.row.isVisibleTo(slot)
    assert (slot.compact_btn.width(), slot.compact_btn.height()) == (40, 40)
    assert slot.compact_btn.toolTip() == "report.pdf"
    texts = [a.text() for a in slot.compact_menu().actions() if not a.isSeparator()]
    assert texts == [a.text() for a in slot.open_control.menu().actions()
                     if not a.isSeparator()] == ["report.pdf", BROWSE_TEXT]
    win.toggle_nav()
    pump(0.35)
    assert not slot.isCompacted and slot.row.isVisibleTo(slot)


def test_bar_row_sits_directly_under_the_subtitle_at_the_left_margin(make_window, tmp_path):
    from paperknife.qt.pages import PAGE_MARGINS
    win = make_window("bar")
    assert win.doc_slot is None
    src = make_pdf(tmp_path / "report.pdf")
    for name in ("CompressTool", "RotateTool", "TocTool", "AnnotateTool", "ReaderTool"):
        assert win.open_tool(name)
        pump(0.05)
        page = win.current_page()
        bar, sub = page.doc_bar, page.subtitle_label
        top_left = bar.mapTo(page, QPoint(0, 0))
        sub_bottom = sub.mapTo(page, QPoint(0, sub.height())).y()
        assert top_left.x() == PAGE_MARGINS[0] == sub.mapTo(page, QPoint(0, 0)).x(), name
        assert 0 <= top_left.y() - sub_bottom <= 1, name           # straight under it
        ctl = bar.open_control
        assert ctl.mapTo(bar, QPoint(0, 0)).x() == 0, name          # the split control first
        assert not bar.chip.isVisibleTo(page), name                 # no document: no chip
    win.open_document(src)
    page = win.current_page()
    assert page.doc_bar.chip.isVisibleTo(page)
    assert page.doc_bar.chip.mapTo(page.doc_bar, QPoint(0, 0)).x() > ctl.width()
    page.doc_bar.chip.clear_btn.click()
    assert win.current_document is None and not page.doc_bar.chip.isVisibleTo(page)


@pytest.mark.parametrize("layout", ["nav", "bar"])
def test_the_empty_state_target(make_window, layout):
    from paperknife.qt.docui import DROP_TEXT, OPEN_TEXT
    from qfluentwidgets import SimpleCardWidget
    win = make_window(layout)
    assert win.open_tool("CompressTool")
    pump(0.05)
    page = win.current_page()
    t = page.drop_target
    assert t.isVisibleTo(page) and t.height() == 200
    assert t.width() == page.content.width()                     # the width of the body
    assert t.label.text() == DROP_TEXT and t.open_control.text() == OPEN_TEXT
    assert abs(t.open_control.geometry().center().x() - t.width() // 2) <= 1
    cards = [c for c in page.content.findChildren(SimpleCardWidget)]
    assert not cards[0].isVisibleTo(page)                         # in place of the first card
    # a workspace shows it in the page view
    assert win.open_tool("AnnotateTool")
    pump(0.05)
    ws = win.current_page()
    assert ws.drop_target.isVisibleTo(ws) and not ws.view.isVisibleTo(ws)
