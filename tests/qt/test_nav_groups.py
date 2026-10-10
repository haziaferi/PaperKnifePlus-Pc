"""Navigation groups fold under their title (owner, 2026-10-10): a click or
Enter / Space on the title folds and unfolds its items, a chevron says
which way, the state survives a new window (PREFS qt_nav_folded), a search
shows matches in folded groups, opening a tool by search unfolds its group,
the icon-only pane shows every icon, and Home and Preferences never fold."""
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

import pytest

from qt_harness import make_pdf, pump

ORGANISE = ["MergeTool", "SplitTool", "RotateTool", "BookmarksTool", "TocTool", "BatchTool"]


@pytest.fixture(autouse=True)
def _settled(window):
    pump(0.3)                       # the titles grow in (150 ms) once the pane expands


def _header(window, section):
    return next(h for s, h, _k in window._sections if s == section)


def _click(w):
    pos = QPointF(20, w.height() / 2)
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        QApplication.sendEvent(w, QMouseEvent(kind, pos, w.mapToGlobal(pos), Qt.LeftButton,
                                              Qt.LeftButton, Qt.NoModifier))


def _key(w, key):
    QApplication.sendEvent(w, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))


def _shown(window, keys):
    return [k for k in keys if not window._items[k].isHidden()]


def test_a_click_on_a_group_title_folds_and_unfolds_it(window):
    from paperknife.qt.shell import CHEVRON_FOLDED, CHEVRON_OPEN, GroupHeader
    h = _header(window, "ORGANISE")
    assert isinstance(h, GroupHeader) and h.text() == "Organise"
    assert _shown(window, ORGANISE) == ORGANISE and not h.folded       # default: all open
    assert h.cursor().shape() == Qt.PointingHandCursor
    assert h.chevron() == CHEVRON_OPEN == 0xE70D                         # down: open
    _click(h)
    assert window.is_folded("ORGANISE") and h.folded and h.isVisible()
    assert _shown(window, ORGANISE) == []
    assert h.chevron() == CHEVRON_FOLDED == 0xE76C                       # right: folded
    assert _shown(window, ["CompressTool"]) == ["CompressTool"]         # other groups stay
    _click(h)
    assert not window.is_folded("ORGANISE") and _shown(window, ORGANISE) == ORGANISE


def test_the_title_takes_the_focus_and_enter_or_space_toggles(window):
    h = _header(window, "CONVERT")
    assert h.focusPolicy() == Qt.StrongFocus
    _key(h, Qt.Key_Return)
    assert window.is_folded("CONVERT") and _shown(window, ["Img2PdfTool"]) == []
    _key(h, Qt.Key_Space)
    assert not window.is_folded("CONVERT") and _shown(window, ["Img2PdfTool"]) == ["Img2PdfTool"]


def test_folding_is_kept_across_a_new_window(window, qapp):
    from paperknife import prefs
    from paperknife.qt.shell import MainWindow
    _click(_header(window, "ORGANISE"))
    _click(_header(window, "CONVERT"))
    assert prefs.Prefs().qt_nav_folded == ["CONVERT", "ORGANISE"]      # saved to prefs.json
    w2 = MainWindow()
    try:
        w2._pointer = lambda: QPoint(0, 0)
        w2.show()
        pump(0.3)
        assert w2.is_folded("ORGANISE") and w2.is_folded("CONVERT")
        assert not w2.is_folded("READ")
        assert _shown(w2, ORGANISE) == [] and _shown(w2, ["ReaderTool"]) == ["ReaderTool"]
    finally:
        w2._close_ok = True
        w2._alive = False
        w2._edge.stop()
        w2.close()
        w2.deleteLater()
        pump(0.02)


def test_a_search_shows_matches_in_a_folded_group_and_clearing_folds_it_again(window):
    h = _header(window, "ORGANISE")
    _click(h)
    window.search.edit.setText("split")
    assert "SplitTool" in window.visible_tools() and "BookmarksTool" in window.visible_tools()
    assert not window._items["MergeTool"].isVisible() and h.isVisibleTo(window)
    assert window.is_folded("ORGANISE")                     # searching does not unfold it
    window.clear_search()
    assert _shown(window, ORGANISE) == [] and h.isVisibleTo(window) and h.folded


def test_opening_a_tool_by_search_unfolds_its_group(window):
    _click(_header(window, "ORGANISE"))
    window.search.edit.setText("rotate")
    window._open_first_match()
    assert type(window.current_page()).__name__ == "RotatePage"
    assert not window.is_folded("ORGANISE")
    window.clear_search()
    assert "RotateTool" in _shown(window, ORGANISE) and _shown(window, ORGANISE) == ORGANISE


def test_a_pdf_dropped_on_home_unfolds_the_reader_s_group(window, tmp_path):
    _click(_header(window, "READ"))
    assert _shown(window, ["ReaderTool"]) == []
    window.show_page("home")
    assert window.forward_drop([make_pdf(tmp_path / "a.pdf")]) == 1
    assert not window.is_folded("READ") and _shown(window, ["ReaderTool"]) == ["ReaderTool"]


def test_folding_the_current_tool_s_group_hides_its_item(window):
    assert window.open_tool("SplitTool")
    _click(_header(window, "ORGANISE"))
    assert window.is_folded("ORGANISE") and window._items["SplitTool"].isHidden()
    assert type(window.current_page()).__name__ == "SplitPage"          # the page stays


def test_the_icon_only_pane_shows_every_icon(window):
    from qfluentwidgets.components.navigation.navigation_panel import NavigationDisplayMode
    for section in ("ORGANISE", "CONVERT", "CONTENT"):
        _click(_header(window, section))
    folded_keys = [k for s, _h, keys in window._sections
                   if s in ("ORGANISE", "CONVERT", "CONTENT") for k in keys]
    assert _shown(window, folded_keys) == []
    window.toggle_nav()
    pump(0.35)
    assert window.navigationInterface.panel.displayMode == NavigationDisplayMode.COMPACT
    assert _shown(window, folded_keys) == folded_keys
    window.toggle_nav()
    pump(0.35)
    assert _shown(window, folded_keys) == []                 # expanded: folded again


def test_home_and_preferences_never_fold(window):
    for _section, header, _keys in window._sections:
        if header is not None:
            _click(header)
    assert not window._items["home"].isHidden()
    assert not window._items["SettingsTool"].isHidden()
    bottom = [h for s, h, _k in window._sections if s == "SETTINGS"]
    assert bottom == [None]                                  # Preferences has no title
