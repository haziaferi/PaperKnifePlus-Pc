"""Window modes: navigation collapse, Compact Mode with edge reveal, the
auto-hiding title bar.  Pointer positions are simulated: _poll_edges gets
explicit positions; the real mouse is never read or moved."""
import pytest
from qt_harness import pump
from PySide6.QtCore import QPoint
from qfluentwidgets.components.navigation.navigation_panel import NavigationDisplayMode

from paperknife.qt import pages, shell
from paperknife.qt.pages import ToolPage


def at(window, x, y):
    window.pointer_at = QPoint(x, y)
    window._poll_edges(window.mapToGlobal(QPoint(x, y)))


class PanelPage(ToolPage):
    """A page with a fake context panel (the workspace template is phase 3)."""

    def __init__(self, tool, window):
        super().__init__("Panel", tool=tool, window=window, scroll=False)
        self.panel_on = True
        self.panel_calls = []

    def has_context(self):
        return True

    def context_shown(self):
        return self.panel_on

    def context_width(self):
        return 280

    def show_context(self, on):
        self.panel_calls.append(on)
        self.panel_on = on


def test_timers_and_slides_use_the_zen_timings(window):
    # The timings drive real timers and animations: check the wiring, not the
    # constants restated (a change detector fails only on a deliberate edit).
    assert window._keep_side_timer.interval() == shell.KEEP_MS
    assert window._keep_ctx_timer.interval() == shell.KEEP_MS
    assert window._hide_top_timer.interval() == shell.TOP_HIDE_MS
    assert window._edge.interval() == shell.POLL_MS
    window.set_compact(True)
    at(window, 2, 400)                              # the left edge slides the nav in
    assert window._anims["side"].duration() == shell.SLIDE_MS
    at(window, 400, 1)                              # the top edge slides the title bar in
    assert window._anims["top"].duration() == shell.TOP_SLIDE_MS


def test_toggle_nav_collapses_and_expands(window):
    panel = window.navigationInterface.panel
    assert panel.displayMode == NavigationDisplayMode.EXPAND
    window.toggle_nav()
    pump(0.35)
    assert panel.displayMode == NavigationDisplayMode.COMPACT
    window.toggle_nav()
    pump(0.35)
    assert panel.displayMode == NavigationDisplayMode.EXPAND


def test_compact_hides_nav_and_header(window):
    window.show_page("CompressTool")
    page = window.current_page()
    window.toggle_compact()
    pump(0.05)
    assert window.compact
    assert not window.navigationInterface.isVisible()
    assert not page.header.isVisible()
    # leaving the page restores it; the next page is compact too
    window.show_page("SplitTool")
    assert page.header.isVisibleTo(page)
    assert not window.current_page().header.isVisibleTo(window.current_page())
    window.toggle_compact()
    pump(0.05)
    assert window.navigationInterface.isVisible()
    assert window.current_page().header.isVisible()


def test_mode_shortcuts_ignored_while_locked(window):
    # R1-20: run_job(lock=True) promises shortcuts are ignored, but Ctrl+Alt+C
    # re-laid out the held page and Ctrl+Alt+S slid the navigation in.
    import threading
    from qt_harness import wait_job
    release = threading.Event()
    window.run_job(lambda stop: release.wait(5), "Working", lock=True)
    panel = window.navigationInterface.panel
    mode = panel.displayMode
    window.toggle_compact()
    assert window.compact is False
    window.toggle_nav()
    pump(0.3)
    assert panel.displayMode == mode
    release.set()
    wait_job(window)
    window.set_compact(True)
    release.clear()
    window.run_job(lambda stop: release.wait(5), "Working", lock=True)
    window.toggle_nav()
    assert window._side_shown is False
    window.toggle_compact()
    assert window.compact is True
    release.set()
    wait_job(window)


@pytest.mark.parametrize("hidden", [True, False])
def test_leaving_compact_restores_the_panel_as_it_was(window, hidden):
    # R1-28: leaving Compact Mode re-opened a panel the user had hidden.
    window.open_tool("ReaderTool")
    page = window.current_page()
    if hidden:
        page.show_context(False)
        pump(pages.SLIDE_MS / 1000 + 0.2)
    assert page.context_shown() is not hidden
    window.toggle_compact()
    pump(pages.SLIDE_MS / 1000 + 0.2)
    assert not page.context_shown()
    window.toggle_compact()
    pump(pages.SLIDE_MS / 1000 + 0.2)
    assert page.context_shown() is not hidden


def test_left_edge_reveals_nav_and_it_leaves_after_keep(window):
    window.set_compact(True)
    at(window, window.width() // 2, 400)
    assert not window.navigationInterface.isVisible()
    at(window, 2, 400)
    assert window._side_shown and window.navigationInterface.isVisible()
    pump(shell.SLIDE_MS / 1000 + 0.1)
    assert window.navigationInterface.x() == 0          # slid fully in
    at(window, 30, 400)                                 # still over it: stays
    pump(shell.KEEP_MS / 1000 + 0.1)
    assert window._side_shown
    at(window, 700, 400)                                # away: keep timer runs
    assert window._keep_side_timer.isActive()
    assert window._keep_side_timer.interval() == shell.KEEP_MS
    pump(shell.KEEP_MS / 1000 + shell.SLIDE_MS / 1000 + 0.15)
    assert not window._side_shown
    assert not window.navigationInterface.isVisible()


def test_pointer_outside_window_still_counts_as_left_edge(window):
    window.set_compact(True)
    at(window, -150, 300)
    assert window._side_shown


def test_right_edge_reveals_context_panel(window, monkeypatch):
    monkeypatch.setitem(pages.QT_PAGES, "AnnotateTool", PanelPage)
    window.show_page("AnnotateTool")
    page = window.current_page()
    window.set_compact(True)
    assert page.panel_calls == [False]                  # Compact Mode hid it
    at(window, window.width() - 2, 400)
    assert page.panel_on and page.panel_calls[-1] is True
    at(window, window.width() - 100, 400)               # over the panel: stays
    pump(shell.KEEP_MS / 1000 + 0.1)
    assert page.panel_on
    at(window, 200, 400)
    pump(shell.KEEP_MS / 1000 + 0.1)
    assert not page.panel_on
    window.set_compact(False)
    assert page.panel_on                                # back on leaving compact


def test_title_bar_hidden_by_default_and_top_edge_reveals(window):
    tb = window.titleBar
    assert not window.title_bar_shown()
    assert tb.y() == -tb.height()
    at(window, 400, 2)
    assert window.title_bar_shown()
    pump(shell.TOP_SLIDE_MS / 1000 + 0.1)
    assert tb.y() == 0
    bx = window.width() - 30                             # over its buttons: stays
    at(window, bx, 15)
    assert window.title_bar_shown()
    assert not window._hide_top_timer.isActive()
    at(window, bx, 400)
    assert window._hide_top_timer.isActive()
    assert window._hide_top_timer.interval() == shell.TOP_HIDE_MS
    window._hide_top_timer.setInterval(100)              # the real 1 s is checked above
    pump(0.1 + shell.TOP_SLIDE_MS / 1000 + 0.15)
    assert not window.title_bar_shown()
    assert tb.y() == -tb.height()


def test_title_bar_makes_way_for_controls_under_it(window):
    """Revealed, the floating bar must not stay over the page's own controls (it caught
    the clicks on the main action at the top right of a maximized window, 2026-10-21)."""
    at(window, 400, 2)
    pump(shell.TOP_SLIDE_MS / 1000 + 0.1)
    assert window.title_bar_shown()
    at(window, window.width() - 260, 20)                 # on the bar, left of its buttons
    assert not window.title_bar_shown()
    assert not window._hide_top_timer.isActive()


def test_compact_top_edge_brings_header_below_bar(window):
    window.show_page("CompressTool")
    page = window.current_page()
    window.set_compact(True)
    assert not page.header.isVisible()
    at(window, 400, 1)
    pump(0.25)
    assert page.header.isVisible()
    assert window.widgetLayout.contentsMargins().top() == window.titleBar.height()
    at(window, 400, 500)                # pointer leaves (the watcher would re-show it)
    window._hide_top()
    pump(0.25)
    assert not page.header.isVisible()
    assert window.widgetLayout.contentsMargins().top() == 0


def test_edge_watch_runs_only_when_needed(window, monkeypatch, qapp, dialogs):
    assert window.edge_watch_active()                   # title bar auto-hides
    assert window._edge.interval() == shell.POLL_MS
    # (showMinimized() needs a real HWND under qframelesswindow; offscreen
    # has none, so the minimised state is simulated)
    monkeypatch.setattr(window, "isMinimized", lambda: True)
    window._update_edge_watch()
    assert not window.edge_watch_active()
    monkeypatch.setattr(window, "isMinimized", lambda: False)
    window._update_edge_watch()
    assert window.edge_watch_active()
    window.hide()
    assert not window.edge_watch_active()
    window.show()
    assert window.edge_watch_active()

    monkeypatch.setenv("PK_TITLEBAR", "always")
    w = shell.MainWindow()
    w._pointer = lambda: w.mapToGlobal(QPoint(300, 300))
    try:
        w.show()
        pump(0.05)
        assert w.title_bar_shown()
        assert not w.edge_watch_active()                # nothing to watch
        w.set_compact(True)
        assert w.edge_watch_active()
        w.set_compact(False)
        assert not w.edge_watch_active()
        assert w.widgetLayout.contentsMargins().top() == w.titleBar.height()
    finally:
        w._close_ok = True
        w._alive = False
        w.close()
        w.deleteLater()


def test_title_bar_double_click_maximises(window, monkeypatch):
    """A double-click on the title bar reaches qframelesswindow's
    TitleBarBase.mouseDoubleClickEvent, which toggles maximise.  Offscreen has
    no HWND to maximise, so the toggle call itself is recorded."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    import qframelesswindow.titlebar as tb_mod
    toggled = []
    monkeypatch.setattr(tb_mod, "toggleMaxState", toggled.append)
    bar = window.titleBar
    p = QPointF(bar.width() / 3, bar.height() / 2)
    ev = QMouseEvent(QEvent.MouseButtonDblClick, p, QPointF(bar.mapToGlobal(p)), Qt.LeftButton,
                     Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(bar, ev)
    pump(0.05)
    assert toggled == [window]


@pytest.mark.parametrize("placement", ["header", "bar"])
def test_primary_action_placement(qapp, monkeypatch, placement):
    monkeypatch.setenv("PK_ACTION", placement)
    page = ToolPage("T", "sub")
    sec = page.secondary("Preview")
    pri = page.primary("Go", danger=True)
    page.resize(800, 600)
    page.show()
    pump(0.02)
    lay = page.header_actions if placement == "header" else page.bar_actions
    assert lay.indexOf(pri) >= 0 and lay.indexOf(sec) >= 0
    assert lay.indexOf(sec) < lay.indexOf(pri)          # secondary left of primary
    assert page.command_bar.isVisible() == (placement == "bar")
    other = page.bar_actions if placement == "header" else page.header_actions
    assert other.indexOf(pri) < 0
    page.close()
    page.deleteLater()


def test_setting_rows_and_dividers(qapp):
    g = pages.card()
    c1 = pages.setting_row(g, "Level", "How hard")
    c2 = pages.setting_row(g, "Keep", "")
    dividers = g.findChildren(pages.Divider)
    assert len(dividers) == 1
    assert c1.parent().findChild(pages.BodyLabel).text() == "Level"
    assert c1.parent().layout().itemAt(0).widget().width() == pages.LABEL_COLUMN \
        or c1.parent().layout().itemAt(0).widget().minimumWidth() == pages.LABEL_COLUMN
    assert c2 is not c1


def test_file_card_choose_uses_dialog_seam(qapp, dialogs, tmp_path):
    from qt_harness import make_pdf
    p = make_pdf(tmp_path / "x.pdf", 1)
    got = []
    fc = pages.file_card(got.append)
    assert fc.button.text() == "Choose file"
    dialogs.open(p)
    fc.choose()
    assert fc.path() == p and got == [p]
    dialogs.open("")                                     # cancelled
    fc.choose()
    assert fc.path() == p and got == [p]
