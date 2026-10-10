"""The document bar (owner's decisions 2026-10-10; phase9/docui-brief.md
section 2, the bar being the one layout): every page builds in light and
dark; the bar is a row directly under the subtitle at the page's left
margin, the Open control then the document's chip; the chip's name gets at
least twice its old 80 px and its whole width when the row has room; pages
show no FileCard and no Open of their own; a page with no document shows
the empty-state target above its options, and the target is the button."""
import pytest
from PySide6.QtCore import QPoint

from qt_harness import make_pdf, pump

NO_FOLLOW = {"MergeTool", "Img2PdfTool", "BatchTool", "SettingsTool", "Doc2PdfTool"}
CHIP_MIN = 2 * 80           # the chip name's least room: twice the 80 px of before
WORKSPACES = ["ReaderTool", "AnnotateTool", "EditTextTool", "FindReplaceTool", "RedactTool"]


def _pages():
    from paperknife.qt.pages import QT_PAGES
    return list(QT_PAGES)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_page_builds_with_the_bar(window, tmp_path, dark):
    from paperknife.qt import theme
    from paperknife.qt.pages import FileCard
    theme.apply_appearance("dark" if dark else "light")
    try:
        src = make_pdf(tmp_path / "a.pdf")
        for name in _pages():
            assert window.open_tool(name), name
            pump(0.02)
            page = window.current_page()
            assert page.isVisible(), name
            if name in NO_FOLLOW:
                continue
            assert not [c for c in page.findChildren(FileCard) if c.isVisibleTo(page)], name
            assert page.drop_target.isVisibleTo(page), name        # no document yet
            assert page.doc_bar.isVisibleTo(page), name
        window.open_document(src)
        for name in _pages():
            assert window.open_tool(name), name
            pump(0.02)
            page = window.current_page()
            if name in NO_FOLLOW:
                continue
            assert not [c for c in page.findChildren(FileCard) if c.isVisibleTo(page)], name
            assert not page.drop_target.isVisibleTo(page), name
            assert page.doc_bar.chip.name_label.text() == "a.pdf", name
            assert "a.pdf" not in page.subtitle_label.text() or \
                page._subtitle == "Open a PDF to start", name         # no " · name" suffix
    finally:
        theme.apply_appearance("light")


def test_the_navigation_holds_no_document_slot(window):
    from paperknife.qt.docui import OpenControl
    assert not window.navigationInterface.findChildren(OpenControl)
    assert not hasattr(window, "doc_slot")


def test_bar_row_sits_directly_under_the_subtitle_at_the_left_margin(window, tmp_path):
    from paperknife.qt.pages import PAGE_MARGINS
    src = make_pdf(tmp_path / "report.pdf")
    for name in ("CompressTool", "RotateTool", "TocTool", "AnnotateTool", "ReaderTool"):
        assert window.open_tool(name)
        pump(0.05)
        page = window.current_page()
        bar, sub = page.doc_bar, page.subtitle_label
        top_left = bar.mapTo(page, QPoint(0, 0))
        sub_bottom = sub.mapTo(page, QPoint(0, sub.height())).y()
        assert top_left.x() == PAGE_MARGINS[0] == sub.mapTo(page, QPoint(0, 0)).x(), name
        assert 0 <= top_left.y() - sub_bottom <= 1, name           # straight under it
        ctl = bar.open_control
        assert ctl.mapTo(bar, QPoint(0, 0)).x() == 0, name          # the split control first
        assert not bar.chip.isVisibleTo(page), name                 # no document: no chip
    window.open_document(src)
    page = window.current_page()
    assert page.doc_bar.chip.isVisibleTo(page)
    assert page.doc_bar.chip.mapTo(page.doc_bar, QPoint(0, 0)).x() > ctl.width()
    page.doc_bar.chip.clear_btn.click()
    assert window.current_document is None and not page.doc_bar.chip.isVisibleTo(page)


# ── the chip's name ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("tool", ["CompressTool", "SplitTool", "AnnotateTool"])
def test_the_chip_shows_a_26_character_name_whole_at_1280x820(window, tmp_path, tool):
    from PySide6.QtWidgets import QLabel
    window.resize(1280, 820)
    name = "Quarterly report final.pdf"
    assert len(name) == 26
    window.open_document(make_pdf(tmp_path / name))
    assert window.open_tool(tool)
    pump(0.05)
    lbl = window.current_page().doc_bar.chip.name_label
    need = lbl.fontMetrics().horizontalAdvance(name)
    assert QLabel.text(lbl) == name and "…" not in QLabel.text(lbl)
    assert lbl.width() >= need, (lbl.width(), need)                   # the row had the room
    assert lbl.minimumWidth() == CHIP_MIN                             # twice the old room


def test_the_chip_cuts_in_the_middle_only_when_the_row_has_no_room(window, tmp_path):
    from PySide6.QtWidgets import QLabel
    window.resize(1280, 820)
    name = "Quarterly report " + "WWWWWW " * 12 + "final.pdf"       # wider than any row
    window.open_document(make_pdf(tmp_path / name))
    assert window.open_tool("CompressTool")
    pump(0.05)
    page = window.current_page()
    lbl = page.doc_bar.chip.name_label
    shown = QLabel.text(lbl)
    assert lbl.fontMetrics().horizontalAdvance(name) > lbl.width() >= CHIP_MIN
    assert "…" in shown and shown.startswith("Quarterly") and shown.endswith(".pdf")
    assert lbl.toolTip().endswith(name)
    # it stays inside the page: the header's actions keep their place
    head = page.header
    assert page.doc_bar.chip.mapTo(head, QPoint(page.doc_bar.chip.width(), 0)).x() <= \
        head.width()


# ── no Open of the page's own ────────────────────────────────────────────────
@pytest.mark.parametrize("tool", WORKSPACES)
def test_workspaces_have_no_open_button_of_their_own(window, dialogs, tmp_path, tool):
    assert window.open_tool(tool)
    pump(0.05)
    page = window.current_page()
    assert not [b for b in page._buttons if b.text() in ("Open", "Open PDF")], tool
    src = make_pdf(tmp_path / "a.pdf")
    dialogs.open(src)
    assert window.page_hook("open")                                   # Ctrl+O, through the bar's
    pump(0.05)
    assert window.current_document == src and page.document_path() == src


# ── the empty-state target ───────────────────────────────────────────────────
def test_the_empty_state_target(window):
    from paperknife.qt.docui import DROP_TEXT, TARGET_FORM_H
    assert window.open_tool("CompressTool")
    pump(0.05)
    page = window.current_page()
    t = page.drop_target
    assert t.isVisibleTo(page) and t.height() == TARGET_FORM_H == 120
    assert t.width() == page.content.width()                     # the width of the body
    assert page.body.itemAt(0).widget() is t                     # at the top of the body
    assert t.label.text() == DROP_TEXT
    # a workspace shows it in the page view
    assert window.open_tool("AnnotateTool")
    pump(0.05)
    ws = window.current_page()
    assert ws.drop_target.isVisibleTo(ws) and not ws.view.isVisibleTo(ws)


def test_the_target_has_no_button_and_a_click_opens_the_dialog(window, dialogs, tmp_path):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QAbstractButton, QApplication
    for tool in ("CompressTool", "AnnotateTool"):
        assert window.open_tool(tool)
        pump(0.05)
        page = window.current_page()
        t = page.drop_target
        assert not t.findChildren(QAbstractButton), tool          # the bar's Open is the one
        assert t.cursor().shape() == Qt.PointingHandCursor
        src = make_pdf(tmp_path / f"{tool}.pdf")
        dialogs.open(src)
        pos = QPointF(t.width() / 3, t.height() / 2)
        for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            QApplication.sendEvent(t, QMouseEvent(kind, pos, t.mapToGlobal(pos), Qt.LeftButton,
                                                  Qt.LeftButton, Qt.NoModifier))
        pump(0.05)
        assert window.current_document == src and page.document_path() == src, tool
        window.clear_current_document()
    page = window.current_page()
    assert page.doc_bar.open_control.isVisibleTo(page)


def test_the_target_takes_the_hover_tint(window):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtWidgets import QApplication
    from paperknife.qt import theme
    assert window.open_tool("CompressTool")
    pump(0.05)
    t = window.current_page().drop_target
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
def test_the_first_options_card_shows_with_no_document(window, tool):
    from qfluentwidgets import SimpleCardWidget
    assert window.open_tool(tool)
    pump(0.05)
    page = window.current_page()
    assert page.document_path() == "" and page.drop_target.isVisibleTo(page)
    cards = [c for c in page.content.findChildren(SimpleCardWidget)]
    assert cards and cards[0].isVisibleTo(page) and cards[0].isEnabled(), tool
    assert page.drop_target.y() < cards[0].mapTo(page.content, cards[0].rect().topLeft()).y()
