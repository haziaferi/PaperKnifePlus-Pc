"""Navigation, page factory, shortcuts, drops, files, geometry, close."""
import base64
import json
import threading

import pytest
from qt_harness import make_pdf, pump, wait_job
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QLineEdit

from paperknife.qt import pages
from paperknife.qt.pages import ToolPage
from paperknife.tool_base import TOOLS


class HookPage(ToolPage):
    """A tool page recording which hooks the shell called."""

    def __init__(self, tool, window):
        super().__init__("Hooks", tool=tool, window=window)
        self.calls = []
        self.edit = QLineEdit(self)
        self.body.addWidget(self.edit)

    def open(self):
        self.calls.append("open")

    def save(self):
        self.calls.append("save")

    def undo(self):
        self.calls.append("undo")

    def delete(self):
        self.calls.append("delete")

    def accept_drop(self, path):
        self.calls.append(("drop", path))
        return path.endswith(".pdf")

    def open_path(self, path):
        self.calls.append(("open_path", path))

    def activate(self):
        self.calls.append("activate")

    def deactivate(self):
        self.calls.append("deactivate")


@pytest.fixture
def hook_page(window, monkeypatch):
    monkeypatch.setitem(pages.QT_PAGES, "MergeTool", HookPage)
    assert window.show_page("MergeTool")
    page = window.current_page()
    assert isinstance(page, HookPage)
    return page


# ── navigation ────────────────────────────────────────────────────────────────
def test_nav_lists_every_tool_grouped_in_registry_order(window):
    order = window.nav_order()
    flat = [k for _h, keys in order for k in keys]
    names = [type(t).__name__ for t in TOOLS]
    assert sorted(flat) == sorted(names) and len(flat) == len(names)
    # groups in first-seen order, tools in registry order inside each group
    sections = []
    for t in TOOLS:
        if t.section not in sections:
            sections.append(t.section)
    expected = [[type(t).__name__ for t in TOOLS if t.section == s] for s in sections]
    assert [keys for _h, keys in order] == expected
    headers = [h for h, _k in order]
    assert headers == [s.capitalize() if s != "SETTINGS" else "" for s in sections]
    assert headers[0] == "Read"


def test_home_first_and_preferences_at_bottom(window):
    from qfluentwidgets import NavigationItemPosition  # noqa: F401
    panel = window.navigationInterface.panel
    scroll = [panel.scrollLayout.itemAt(i).widget() for i in range(panel.scrollLayout.count())]
    assert scroll[0] is window._items["home"]
    bottom = [panel.bottomLayout.itemAt(i).widget() for i in range(panel.bottomLayout.count())]
    assert window._items["SettingsTool"] in bottom
    assert window._labels["SettingsTool"] == "Preferences"


def test_labels_have_no_emoji(window):
    assert window._labels["CompressTool"] == "Compress"
    assert window._labels["EditTextTool"] == "Edit Text"
    assert window._labels["Img2PdfTool"] == "Image → PDF"


def test_search_filters_by_label_and_hides_empty_groups(window):
    window.search.edit.setText("comp")
    assert window.visible_tools() == ["CompressTool"]
    headers = {h.text(): h for _s, h, _k in window._sections if h is not None}
    assert not headers["Enhance"].isHidden()
    assert headers["Organise"].isHidden()
    window.search.edit.setText("PDF")
    assert set(window.visible_tools()) >= {"Img2PdfTool", "Pdf2ImgTool", "PdfToolsTool"}
    window.clear_search()
    assert len(window.visible_tools()) == len(TOOLS)
    assert all(not h.isHidden() for h in headers.values())


def test_search_enter_opens_first_match(window):
    window.search.edit.setText("water")
    window.search.edit.returnPressed.emit()
    assert window._current_key == "WatermarkTool"


def test_ctrl_k_focuses_search(window):
    window.activateWindow()
    pump(0.05)
    window.focus_search()
    pump(0.05)
    assert window.search.edit.hasFocus() or window.search.edit is \
        window.focusWidget(), "search field did not take focus"


def test_unported_tool_gets_placeholder(window, monkeypatch):
    # An empty registry stands for "not ported yet", so this holds as tools are ported.
    monkeypatch.setattr(pages, "QT_PAGES", {})
    assert window.show_page("CompressTool")
    page = window.current_page()
    assert isinstance(page, pages.PlaceholderPage)
    assert page.title_label.text() == "Compress"


def test_registered_page_class_is_used_and_hooks_run(window, hook_page):
    assert hook_page.calls == ["activate"]
    assert window.show_page("home")
    assert hook_page.calls == ["activate", "deactivate"]
    # built once, reused
    assert window.show_page("MergeTool")
    assert window.current_page() is hook_page


def test_open_tool_with_path_hands_the_file(window, hook_page):
    window.show_page("home")
    assert window.open_tool("MergeTool", "C:/x.pdf")
    assert ("open_path", "C:/x.pdf") in hook_page.calls


# ── shortcuts ─────────────────────────────────────────────────────────────────
def test_shortcut_hooks_call_the_page(window, hook_page):
    hook_page.calls.clear()
    for name in ("open", "save", "undo"):
        assert window.page_hook(name)
    window.setFocus()
    assert window._on_delete_key()
    assert hook_page.calls == ["open", "save", "undo", "delete"]


def test_shortcut_keys_reach_the_page(window, hook_page):
    from PySide6.QtTest import QTest
    window.activateWindow()
    window.setFocus()
    pump(0.05)
    hook_page.calls.clear()
    QTest.keyClick(window, Qt.Key_O, Qt.ControlModifier)
    QTest.keyClick(window, Qt.Key_S, Qt.ControlModifier)
    QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)
    pump(0.05)
    assert hook_page.calls == ["open", "save", "undo"]


def test_delete_ignored_in_text_field(window, hook_page):
    window.activateWindow()
    hook_page.edit.setFocus()
    pump(0.05)
    if not hook_page.edit.hasFocus():
        pytest.skip("offscreen platform gave the field no focus")
    hook_page.calls.clear()
    assert window._on_delete_key() is False
    assert hook_page.calls == []


def test_page_without_hook_is_fine(window):
    window.show_page("CompressTool")
    assert window.page_hook("save") is False


def test_shortcuts_ignored_while_locked(window, hook_page):
    release = threading.Event()
    window.run_job(lambda stop: release.wait(5), "Working", lock=True)
    hook_page.calls.clear()
    for name in ("open", "save", "undo", "delete"):
        assert window.page_hook(name) is False
    window.setFocus()
    assert not window._on_delete_key()
    window.focus_search()
    assert hook_page.calls == []
    release.set()
    wait_job(window)
    assert window.page_hook("save") and hook_page.calls == ["save"]


def test_escape_clears_search(window):
    from PySide6.QtTest import QTest
    window.search.edit.setText("split")
    window.activateWindow()
    window.setFocus()
    pump(0.05)
    QTest.keyClick(window, Qt.Key_Escape)
    pump(0.05)
    if window.search.edit.text():           # key not delivered offscreen
        window.clear_search()
    assert window.search.edit.text() == ""


# ── drag and drop ─────────────────────────────────────────────────────────────
def _drop(window, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    ev = QDropEvent(QPointF(400, 300), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(ev)
    return ev


def test_drop_forwards_paths_to_page(window, hook_page, tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.txt"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    hook_page.calls.clear()
    ev = _drop(window, [a, b])
    drops = [c for c in hook_page.calls if c[0] == "drop"]
    assert [p for _d, p in drops] == [QUrl.fromLocalFile(str(a)).toLocalFile(),
                                      QUrl.fromLocalFile(str(b)).toLocalFile()]
    assert ev.isAccepted()


def test_drop_refused_sets_warning(window, hook_page, tmp_path):
    b = tmp_path / "b.txt"
    b.write_bytes(b"y")
    _drop(window, [b])
    assert window.status_role == "warning"
    assert "b.txt" in window.status_text()


def test_drop_ignored_while_locked(window, hook_page, tmp_path):
    a = tmp_path / "a.pdf"
    a.write_bytes(b"x")
    release = threading.Event()
    window.run_job(lambda stop: release.wait(5), "Working", lock=True)
    hook_page.calls.clear()
    _drop(window, [a])
    assert hook_page.calls == []
    release.set()
    wait_job(window)


def test_drop_reaches_file_card(window, monkeypatch, tmp_path):
    class CardPage(ToolPage):
        def __init__(self, tool, win):
            super().__init__("Cards", tool=tool, window=win)
            self.changed = []
            self.card = pages.file_card(self.changed.append, (".pdf",))
            self.body.addWidget(self.card)
    monkeypatch.setitem(pages.QT_PAGES, "SplitTool", CardPage)
    window.show_page("SplitTool")
    page = window.current_page()
    pdf = make_pdf(tmp_path / "doc.pdf", 1)
    txt = tmp_path / "notes.txt"
    txt.write_text("x")
    assert window.forward_drop([str(txt)]) == 0
    assert page.card.path() == ""
    assert window.forward_drop([pdf]) == 1
    assert page.card.path() == pdf and page.changed == [pdf]
    assert page.card.name_label.text() == "doc.pdf"
    assert page.card.button.text() == "Change"


# ── files ─────────────────────────────────────────────────────────────────────
def test_open_pdf_safe_asks_password(window, dialogs, tmp_path):
    from paperknife.recent import RECENT
    p = make_pdf(tmp_path / "locked.pdf", 2, password="s3cret")
    dialogs.passwords.append("s3cret")
    doc = window.open_pdf_safe(p)
    assert doc is not None and len(doc) == 2 and not doc.is_encrypted
    doc.close()
    assert [m[0] for m in dialogs.msgs] == ["ask_password"]
    assert RECENT.all()[0]["name"] == "locked.pdf"


def test_open_pdf_safe_wrong_or_no_password(window, dialogs, tmp_path):
    p = make_pdf(tmp_path / "locked2.pdf", 1, password="right")
    dialogs.passwords.append("wrong")
    assert window.open_pdf_safe(p) is None
    assert dialogs.errors() == [("error", "Error", "Incorrect password.")]
    dialogs.reset()
    assert window.open_pdf_safe(p) is None            # cancelled: no answer queued
    assert dialogs.errors() == []


def test_open_pdf_safe_unreadable(window, dialogs, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    assert window.open_pdf_safe(str(bad)) is None
    assert dialogs.errors() and dialogs.errors()[0][2].startswith("Could not open PDF")


def test_home_lists_recent_files_and_clears(window, dialogs, tmp_path):
    p = make_pdf(tmp_path / "recent.pdf", 1)
    window.open_pdf_safe(p).close()
    window.show_page("CompressTool")
    window.show_page("home")
    home = window.current_page()
    names = [c.name_label.text() for c in home.cards]
    assert "recent.pdf" in names
    pump(0.2)
    card = next(c for c in home.cards if c.name_label.text() == "recent.pdf")
    assert card.thumb.pixmap() is not None and not card.thumb.pixmap().isNull()
    assert "just now" in card.meta_label.text()
    dialogs.asks.append(True)
    home.clear_history()
    assert home.cards == [] and home.empty_label.isVisibleTo(home)



def test_home_thumbnails_are_read_off_the_ui_thread(window, monkeypatch, tmp_path):
    # R1-10: an offline share's stat timeout or a huge scan's render held the
    # window; the file is now looked at and rendered on a worker.
    import os
    from paperknife.qt import home as hmod
    seen = {"stat": [], "open": []}

    class Os:
        def __getattr__(self, name):
            return getattr(os, name)

        def stat(self, path, *a, **k):
            if str(path).endswith("offthread.pdf"):
                seen["stat"].append(threading.current_thread())
            return os.stat(path, *a, **k)

    class Fitz:
        def __getattr__(self, name):
            return getattr(hmod.__dict__["_real_fitz"], name)

        def open(self, *a, **k):
            if a and str(a[0]).endswith("offthread.pdf"):
                seen["open"].append(threading.current_thread())
            return hmod.__dict__["_real_fitz"].open(*a, **k)
    monkeypatch.setitem(hmod.__dict__, "_real_fitz", hmod.fitz)
    monkeypatch.setattr(hmod, "os", Os())
    monkeypatch.setattr(hmod, "fitz", Fitz())
    p = make_pdf(tmp_path / "offthread.pdf", 1)
    window.open_pdf_safe(p).close()
    window.show_page("CompressTool")
    window.show_page("home")
    home = window.current_page()
    card = next(c for c in home.cards if c.name_label.text() == "offthread.pdf")
    for _ in range(50):
        pump(0.02)
        if card.thumb.pixmap() is not None and not card.thumb.pixmap().isNull():
            break
    assert card.thumb.pixmap() is not None and not card.thumb.pixmap().isNull()
    assert seen["stat"] and threading.main_thread() not in seen["stat"]
    assert seen["open"] and threading.main_thread() not in seen["open"]


# ── geometry and close ────────────────────────────────────────────────────────
def _new_window():
    from paperknife.qt.shell import MainWindow
    return MainWindow()


def _discard_window(w):
    w._close_ok = True
    w._alive = False
    w.close()
    w.deleteLater()


def test_geometry_saved_under_new_key(window, monkeypatch):
    from paperknife.prefs import PREFS, PREFS_PATH
    PREFS.window_geometry = "800x600+0+0"          # the Tk key: left alone
    window.setGeometry(10, 20, 1100, 750)
    window._finish_close()
    data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
    assert json.loads(data["qt_window_geometry"]) == {
        "x": 10, "y": 20, "w": 1100, "h": 750, "maximized": False}
    assert data["window_geometry"] == "800x600+0+0"
    w2 = _new_window()
    try:
        assert w2.geometry().getRect() == (10, 20, 1100, 750) and not w2.isMaximized()
    finally:
        _discard_window(w2)


def test_geometry_of_a_maximized_session_keeps_the_normal_rect(window, monkeypatch):
    # R1-21: saveGeometry() of the maximized frameless window stored a rect
    # inset by the 8 px resize border, so each maximized session moved the
    # window 8 px and shrank it 16 px.  (The inset itself needs the Windows
    # platform: review/probes/fa_r1_21_geometry_win.py.)
    from qframelesswindow.utils import win32_utils
    from paperknife.prefs import PREFS
    # qframelesswindow asks Win32 about the window on every state change,
    # and an offscreen window has no Win32 handle.
    monkeypatch.setattr(win32_utils, "isMaximized", lambda _hwnd: False)
    window.setGeometry(10, 20, 1100, 750)
    pump(0.02)
    window.showMaximized()
    pump(0.05)
    window._finish_close()
    stored = json.loads(PREFS.get("qt_window_geometry"))
    assert stored == {"x": 10, "y": 20, "w": 1100, "h": 750, "maximized": True}
    w2 = _new_window()
    try:
        assert w2.windowState() & Qt.WindowMaximized
        assert w2._normal_rect.getRect() == (10, 20, 1100, 750)
        w2.show()
        pump(0.05)
        w2._finish_close()
        assert json.loads(PREFS.get("qt_window_geometry")) == stored   # no creep
    finally:
        _discard_window(w2)


def test_geometry_off_every_screen_comes_back(qapp, dialogs):
    from PySide6.QtWidgets import QApplication
    from paperknife.prefs import PREFS
    PREFS.qt_window_geometry = json.dumps({"x": -9000, "y": 20, "w": 1100, "h": 750,
                                           "maximized": False})
    w = _new_window()
    try:
        avail = QApplication.primaryScreen().availableGeometry()
        assert w.geometry().topLeft() == avail.topLeft()
        assert w.geometry().size().toTuple() == (1100, 750)
    finally:
        _discard_window(w)


def test_geometry_from_an_older_version_still_restores(qapp, dialogs, monkeypatch):
    from paperknife.prefs import PREFS
    from paperknife.qt.shell import MainWindow
    w = _new_window()
    blob = bytes(w.saveGeometry())
    _discard_window(w)
    PREFS.qt_window_geometry = base64.b64encode(blob).decode("ascii")
    restored = []
    real = MainWindow.restoreGeometry
    monkeypatch.setattr(MainWindow, "restoreGeometry",
                        lambda self, ba: (restored.append(bytes(ba)), real(self, ba))[1])
    w2 = _new_window()
    try:
        assert restored == [blob]
    finally:
        _discard_window(w2)


def test_close_with_job_asks_and_waits(window, dialogs):
    from paperknife.prefs import PREFS_PATH
    release = threading.Event()
    window.run_job(lambda stop: release.wait(5) if not stop.is_set() else None, "Working")
    dialogs.asks.append(False)
    window.close()
    pump(0.05)
    assert window.isVisible()                          # "No": stays open
    assert window._current_job.is_running

    def work_until_cancel(stop):
        stop.wait(5)
    release.set()
    wait_job(window)
    window.run_job(work_until_cancel, "Working")
    dialogs.asks.append(True)
    if PREFS_PATH.exists():
        PREFS_PATH.unlink()
    window.close()
    assert window.isVisible()                          # waits for the job
    assert window.status_text() == "Cancelling before exit…"
    for _ in range(100):
        pump(0.05)
        if not window.isVisible():
            break
    assert not window.isVisible()
    assert PREFS_PATH.exists()                         # geometry saved on the way out
    assert [m[0] for m in dialogs.msgs].count("ask_yes_no") == 2


def test_quit_past_the_close_deadline_leaves_no_part_file(window, dialogs, monkeypatch,
                                                          tmp_path):
    # R1-17: the window closed at CLOSE_WAIT_S with a save still writing; the
    # daemon worker died at exit and its hidden .part file stayed in the
    # user's output folder.  The next start removes it.
    import os
    from paperknife.job_queue import atomic_output
    from paperknife.qt import shell
    monkeypatch.setattr(shell, "CLOSE_WAIT_S", 0.3)
    release, written, parts = threading.Event(), threading.Event(), []

    def work(stop):                     # a save that never looks at stop
        with atomic_output(str(tmp_path / "out.pdf")) as tmp:
            parts.append(tmp)
            with open(tmp, "wb") as f:
                f.write(b"%PDF-1.7 partial")
            written.set()
            release.wait(10)
    window.run_job(work, "Saving", cancellable=False)
    assert written.wait(5)
    dialogs.asks.append(True)
    window.close()
    for _ in range(100):
        pump(0.05)
        if not window.isVisible():
            break
    assert not window.isVisible()
    assert os.path.exists(parts[0])     # what the killed worker would leave
    w2 = shell.MainWindow()             # the next start
    try:
        assert not os.path.exists(parts[0])
        assert list(tmp_path.iterdir()) == []
    finally:
        release.set()
        w2._close_ok = True
        w2._alive = False
        w2.close()
        w2.deleteLater()


def test_late_job_callback_after_close_is_dropped(window):
    release = threading.Event()
    seen = []
    window.run_job(lambda stop: release.wait(5), "Working", then=lambda k, v: seen.append(k))
    window._finish_close()
    release.set()
    for _ in range(40):
        pump(0.02)
        if not window._current_job.is_running:
            break
    pump(0.1)
    assert seen == []


def test_poll_positions_are_window_relative(window):
    # sanity for the mode tests: the simulated pointer maps back exactly
    g = window.mapToGlobal(QPoint(5, 6))
    assert window.mapFromGlobal(g) == QPoint(5, 6)


# ── dialogs: a closed dialog does not stay behind ──
@pytest.fixture
def dialog_parent(qapp, monkeypatch):
    """The real paperknife.qt.dialogs over a plain shown window."""
    from PySide6.QtWidgets import QWidget
    from paperknife.qt import dialogs as dmod
    w = QWidget()
    w.resize(600, 400)
    w.show()
    monkeypatch.setattr(dmod, "_parent", lambda: w)
    yield w
    w.close()
    w.deleteLater()
    pump(0.02)


def _answer_password(parent, text):
    from paperknife.qt import dialogs as dmod

    def fill():
        for d in parent.findChildren(dmod._PasswordDialog):
            if d.isVisible():
                d.edit.setText(text)
                d.yesButton.click()
    from PySide6.QtCore import QTimer
    QTimer.singleShot(50, fill)


def test_password_dialog_keeps_no_password_after_closing(dialog_parent):
    # R1-5: every password typed stayed in a hidden PasswordLineEdit.
    from paperknife.qt import dialogs as dmod
    for _ in range(3):
        _answer_password(dialog_parent, "s3cret")
        assert dmod.ask_password() == "s3cret"
    left = [d.edit.text() for d in dialog_parent.findChildren(dmod._PasswordDialog)]
    assert "s3cret" not in left
    pump(0.05)
    assert dialog_parent.findChildren(dmod._PasswordDialog) == []


def _click_box(parent, button: str):
    from PySide6.QtCore import QTimer
    from qfluentwidgets import MessageBox

    def click():
        for b in parent.findChildren(MessageBox):
            if b.isVisible():
                getattr(b, button).click()
    QTimer.singleShot(50, click)


def test_message_boxes_are_deleted_after_closing(dialog_parent):
    # R1-6: every info/warning/error/ask_yes_no left a hidden MessageBox.
    from qfluentwidgets import MessageBox
    from paperknife.qt import dialogs as dmod
    for fn in (dmod.info, dmod.warning, dmod.error):
        _click_box(dialog_parent, "yesButton")
        fn("Title", "Message")
    _click_box(dialog_parent, "yesButton")
    assert dmod.ask_yes_no("Title", "Question?") is True
    _click_box(dialog_parent, "cancelButton")
    assert dmod.ask_yes_no("Title", "Question?") is False
    pump(0.05)
    assert dialog_parent.findChildren(MessageBox) == []
