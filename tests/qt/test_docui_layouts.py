"""The two layouts for opening a file (env PK_DOCUI=nav|bar, default nav;
phase9/docui-brief.md section 2): every page builds in both, light and
dark; the open control is where the owner put it (nav: the slot directly
under the search box, full pane width, 40 px; bar: a row directly under the
subtitle at the page's left margin); the collapsed navigation shows a 40x40
file icon button with the same list; pages show no FileCard; a page with no
document shows the empty-state target above its options (2026-10-10 fixes:
the slot is one full-width button, the target is the button itself)."""
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
    slot = win.doc_slot
    # no document: "No document" and the Open split control
    assert slot.empty_row.isVisibleTo(slot) and not slot.doc_button.isVisibleTo(slot)
    assert slot.name_label.text() == NO_DOCUMENT
    assert slot.open_control.text() == OPEN_TEXT
    src = make_pdf(tmp_path / "r.pdf")
    win.open_document(src)
    # a document: one full-width drop-down button, no separate x or Open
    btn = slot.doc_button
    assert btn.isVisibleTo(slot) and not slot.empty_row.isVisibleTo(slot)
    assert btn.width() == slot.width() and btn.x() == 0
    assert btn.text() == btn.name() == "r.pdf" and btn.toolTip() == src
    win.clear_current_document()
    assert slot.empty_row.isVisibleTo(slot)


def test_nav_slot_name_gets_the_whole_slot_and_is_cut_only_when_it_must(make_window, tmp_path):
    win = make_window("nav")
    win.resize(1280, 820)
    pump(0.05)
    btn = win.doc_slot.doc_button
    win.open_document(make_pdf(tmp_path / "report.pdf"))
    pump(0.02)
    # the name's room: the slot's width less the icon's and the arrow's paddings
    assert btn.room() >= btn.width() - 36 - 31 - 2
    fm = btn.fontMetrics()
    name = "a" * 26 + ".pdf"                        # 30 characters
    while fm.horizontalAdvance(name) > btn.room():  # (offscreen fonts run wide)
        name = name[1:]
    src = make_pdf(tmp_path / name)
    win.open_document(src)
    pump(0.02)
    assert btn.text() == name and "…" not in btn.text()   # fits: shown whole
    long_name = "Quarterly report final v02 with appendix and notes.pdf"
    win.open_document(make_pdf(tmp_path / long_name))
    pump(0.02)
    shown = btn.text()
    assert "…" in shown and shown.startswith("Q") and shown.endswith(".pdf")  # middle cut
    assert fm.horizontalAdvance(shown) <= btn.room()


def test_nav_slot_menu_browse_recent_then_clear(make_window, dialogs, tmp_path):
    from paperknife.qt.docui import BROWSE_TEXT, CLEAR_TEXT, slot_menu
    from paperknife.recent import RECENT
    win = make_window("nav")
    old, cur = make_pdf(tmp_path / "old.pdf"), make_pdf(tmp_path / "cur.pdf")
    RECENT.push(old, 3)
    RECENT.push(cur, 3)
    win.open_document(cur)
    menu = slot_menu(win)
    acts = menu.actions()                                       # (RoundMenu lists no separators)
    assert [a.text() for a in acts] == [BROWSE_TEXT, "old.pdf", CLEAR_TEXT]   # current left out
    acts[1].trigger()
    assert win.current_document.endswith("old.pdf")
    slot_menu(win).actions()[-1].trigger()
    assert win.current_document is None
    dialogs.open(cur)
    slot_menu(win).actions()[0].trigger()                       # Browse…
    assert win.current_document.endswith("cur.pdf")


def test_nav_slot_collapses_to_a_file_icon_button_with_the_same_list(make_window, tmp_path):
    from paperknife.qt.docui import slot_menu
    from paperknife.recent import RECENT
    win = make_window("nav")
    src = make_pdf(tmp_path / "report.pdf")
    other = make_pdf(tmp_path / "other.pdf")
    RECENT.push(other, 3)
    RECENT.push(src, 3)
    win.open_document(src)
    win.toggle_nav()
    pump(0.35)
    slot = win.doc_slot
    assert slot.isCompacted and (slot.width(), slot.height()) == (40, 40)
    assert slot.compact_btn.isVisibleTo(slot) and not slot.doc_button.isVisibleTo(slot)
    assert not slot.empty_row.isVisibleTo(slot)
    assert (slot.compact_btn.width(), slot.compact_btn.height()) == (40, 40)
    assert slot.compact_btn.toolTip() == "report.pdf"
    texts = [a.text() for a in slot.compact_menu().actions()]
    assert texts == [a.text() for a in slot_menu(win).actions()]
    win.toggle_nav()
    pump(0.35)
    assert not slot.isCompacted and slot.doc_button.isVisibleTo(slot)


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
    from paperknife.qt.docui import DROP_TEXT, TARGET_FORM_H
    win = make_window(layout)
    assert win.open_tool("CompressTool")
    pump(0.05)
    page = win.current_page()
    t = page.drop_target
    assert t.isVisibleTo(page) and t.height() == TARGET_FORM_H == 120
    assert t.width() == page.content.width()                     # the width of the body
    assert page.body.itemAt(0).widget() is t                     # at the top of the body
    assert t.label.text() == DROP_TEXT
    # a workspace shows it in the page view
    assert win.open_tool("AnnotateTool")
    pump(0.05)
    ws = win.current_page()
    assert ws.drop_target.isVisibleTo(ws) and not ws.view.isVisibleTo(ws)


@pytest.mark.parametrize("layout", ["nav", "bar"])
def test_the_target_has_no_button_and_a_click_opens_the_dialog(make_window, dialogs, tmp_path,
                                                               layout):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QAbstractButton, QApplication
    win = make_window(layout)
    for tool in ("CompressTool", "AnnotateTool"):
        assert win.open_tool(tool)
        pump(0.05)
        page = win.current_page()
        t = page.drop_target
        assert not t.findChildren(QAbstractButton), tool          # the layout's Open is the one
        assert t.cursor().shape() == Qt.PointingHandCursor
        src = make_pdf(tmp_path / f"{tool}.pdf")
        dialogs.open(src)
        pos = QPointF(t.width() / 3, t.height() / 2)
        for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            QApplication.sendEvent(t, QMouseEvent(kind, pos, t.mapToGlobal(pos), Qt.LeftButton,
                                                  Qt.LeftButton, Qt.NoModifier))
        pump(0.05)
        assert win.current_document == src and page.document_path() == src, tool
        win.clear_current_document()
    # the one Open control of the layout is still there, in both states
    page = win.current_page()
    ctl = win.doc_slot if layout == "nav" else page.doc_bar
    assert ctl.open_control.isVisibleTo(ctl)


def test_the_target_takes_the_hover_tint(make_window):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtWidgets import QApplication
    from paperknife.qt import theme
    win = make_window("nav")
    assert win.open_tool("CompressTool")
    pump(0.05)
    t = win.current_page().drop_target
    before = t.grab().toImage().pixelColor(t.width() // 2, 8)
    p = QPointF(10, 10)
    QApplication.sendEvent(t, QEnterEvent(p, p, t.mapToGlobal(p)))
    pump(0.02)
    after = t.grab().toImage().pixelColor(t.width() // 2, 8)
    assert t.hovered and after != before
    QApplication.sendEvent(t, QEvent(QEvent.Leave))
    assert not t.hovered
    assert theme.color("tint_hover").alpha() > 0


@pytest.mark.parametrize("tool", ["CompressTool", "SplitTool", "WatermarkTool", "MetadataTool",
                                  "PasswordTool", "RotateTool", "TocTool", "BookmarksTool"])
def test_the_first_options_card_shows_with_no_document(make_window, tool):
    from qfluentwidgets import SimpleCardWidget
    win = make_window("nav")
    assert win.open_tool(tool)
    pump(0.05)
    page = win.current_page()
    assert page.document_path() == "" and page.drop_target.isVisibleTo(page)
    cards = [c for c in page.content.findChildren(SimpleCardWidget)]
    assert cards and cards[0].isVisibleTo(page) and cards[0].isEnabled(), tool
    assert page.drop_target.y() < cards[0].mapTo(page.content, cards[0].rect().topLeft()).y()
