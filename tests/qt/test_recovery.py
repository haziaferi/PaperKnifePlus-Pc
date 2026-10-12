"""Crash recovery (owner's choice 2026-10-12): unsaved edits are copied while
the app runs; after a crash the next start asks "Recover unsaved changes?"
with Discard / Recover, and Recover opens each in its tool, as unsaved."""
import pymupdf as fitz
import pytest

from conftest import close_test_window
from paperknife.core import recovery
from qt_harness import make_pdf, pump, wait_job


def _new_window():
    from PySide6.QtCore import QPoint
    from paperknife.qt.shell import MainWindow
    w = MainWindow()
    w.move(0, 0)
    w.pointer_at = QPoint(w.width() // 2, w.height() // 2)
    w._pointer = lambda: w.mapToGlobal(w.pointer_at)
    w.show()
    pump(0.1)                   # the start's question runs once the window is up
    return w


def _crash(w):
    """As if the app died: its recovery folder stays, its lock goes."""
    w._recovery_timer.stop()
    w._recovery.release()
    w._recovery = None
    close_test_window(w)


def _replace(window, dialogs, page, find, repl):
    page.find_edit.setText(find)
    page.repl_edit.setText(repl)
    dialogs.asks.append(True)                   # "Replace ALL occurrences…?"
    page.replace_all()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def _edited(window, dialogs, tmp_path, password=None):
    src = make_pdf(tmp_path / "report.pdf", pages=2, text="Page {n} of the old report",
                   password=password)
    if password:
        dialogs.passwords.append(password)
    assert window.open_tool("FindReplaceTool", src)
    page = window.current_page()
    _replace(window, dialogs, page, "old", "new")
    assert page.is_dirty()
    return src, page


def _text(doc):
    return [" ".join(p.get_text().split()) for p in doc]


def test_edits_are_copied_and_a_crash_offers_them_back(qapp, window, dialogs, tmp_path):
    src, page = _edited(window, dialogs, tmp_path)
    # The job's end copied the edits at once: no wait for the timer.
    assert window._recovery.keys() == ["FindReplaceTool"]
    _crash(window)
    dialogs.recovers.append(True)
    w = _new_window()
    try:
        asked = [m for m in dialogs.msgs if m[0] == "ask_recover"]
        assert asked and asked[0][1] == "Recover unsaved changes?"
        assert asked[0][2].startswith("report.pdf — Find & Replace, ")
        p = w.current_page()
        assert w._current_key == "FindReplaceTool" and p.is_dirty()
        assert p.document_path() == src
        assert _text(p._doc) == ["Page 1 of the new report", "Page 2 of the new report"]
        assert recovery.orphaned() == []                # taken in by the new app
        assert w._recovery.keys() == ["FindReplaceTool"]
    finally:
        close_test_window(w)


def test_discard_removes_the_copies(qapp, window, dialogs, tmp_path):
    _edited(window, dialogs, tmp_path)
    _crash(window)
    dialogs.recovers.append(False)
    w = _new_window()
    try:
        assert w._current_key == "home"
        assert recovery.orphaned() == []
        assert w._recovery.keys() == []
    finally:
        close_test_window(w)


def test_closing_the_question_keeps_the_copies_for_the_next_start(qapp, window, dialogs,
                                                                  tmp_path):
    _edited(window, dialogs, tmp_path)
    _crash(window)
    dialogs.recovers.append(None)
    w = _new_window()
    try:
        assert w._current_key == "home"
        assert [e.key for e in recovery.orphaned()] == ["FindReplaceTool"]
    finally:
        close_test_window(w)


def test_a_save_and_a_normal_exit_leave_nothing(qapp, window, dialogs, tmp_path):
    _, page = _edited(window, dialogs, tmp_path)
    folder = window._recovery.folder
    dialogs.save(tmp_path / "saved.pdf")
    page.save()
    wait_job(window)
    assert not page.is_dirty()
    assert window._recovery.keys() == []           # the save dropped the copy
    window._finish_close()
    assert not folder.exists() and recovery.orphaned() == []


def test_discarded_edits_drop_the_copy(qapp, window, dialogs, tmp_path):
    _edited(window, dialogs, tmp_path)
    dialogs.unsaved.append("discard")
    assert window.show_page("home")
    assert window._recovery.keys() == []


def test_unchanged_edits_are_not_written_again(qapp, window, dialogs, tmp_path, monkeypatch):
    _edited(window, dialogs, tmp_path)
    writes = []
    real = window._recovery.write
    monkeypatch.setattr(window._recovery, "write", lambda *a: (writes.append(a[0]), real(*a)))
    window.snapshot_edits()
    window.snapshot_edits()
    assert writes == []


def test_a_protected_file_s_copy_keeps_its_password(qapp, window, dialogs, tmp_path):
    _edited(window, dialogs, tmp_path, password="s3cret")
    copy = (window._recovery.folder / "FindReplaceTool.pdf").read_bytes()
    with fitz.open("pdf", copy) as d:
        assert d.needs_pass                         # not readable without it
    _crash(window)
    dialogs.recovers.append(True)
    dialogs.passwords.append("s3cret")
    w = _new_window()
    try:
        p = w.current_page()
        assert _text(p._doc)[0] == "Page 1 of the new report" and p.is_dirty()
    finally:
        close_test_window(w)


def test_a_running_app_s_edits_are_not_offered(qapp, window, dialogs, tmp_path):
    _edited(window, dialogs, tmp_path)
    w = _new_window()                               # no question queued: none asked
    try:
        assert w._current_key == "home"
    finally:
        close_test_window(w)


def _rotated(window, tmp_path):
    src = make_pdf(tmp_path / "pages.pdf", pages=3)
    assert window.open_tool("RotateTool", src)
    pump(0.05)
    page = window.current_page()
    page.select(2)
    page.rotate(90)
    page.select(2)
    page.move_pages(-1)
    assert page.is_dirty()
    return src


def test_rotate_edits_come_back_on_the_file(qapp, window, dialogs, tmp_path):
    src = _rotated(window, tmp_path)
    window.snapshot_edits()
    _crash(window)
    dialogs.recovers.append(True)
    w = _new_window()
    try:
        p = w.current_page()
        assert w._current_key == "RotateTool" and p.is_dirty()
        assert p.document_path() == src
        assert p.order() == [0, 2, 1] and p._extra == {0: 0, 1: 0, 2: 90}
    finally:
        close_test_window(w)


def test_metadata_edits_come_back(qapp, window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    assert window.open_tool("MetadataTool", src)
    window.current_page().fields["title"].setText("A new title")
    window.snapshot_edits()
    assert window._recovery.keys() == ["MetadataTool"]
    _crash(window)
    dialogs.recovers.append(True)
    w = _new_window()
    try:
        p = w.current_page()
        assert p.fields["title"].text() == "A new title" and p.is_dirty()
    finally:
        close_test_window(w)


def test_bookmark_edits_come_back(qapp, window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    assert window.open_tool("TocTool", src)
    toc = window.current_page()
    toc.title_edit.setText("Chapter")
    toc.page_edit.setText("2")
    toc._add()
    window.snapshot_edits()
    _crash(window)
    dialogs.recovers.append(True)
    w = _new_window()
    try:
        p = w.current_page()
        assert [e[1:] for e in p._toc] == [["Chapter", 2]] and p.is_dirty()
    finally:
        close_test_window(w)


def test_edits_for_a_file_that_is_gone_are_reported(qapp, window, dialogs, tmp_path):
    src = _rotated(window, tmp_path)
    window.snapshot_edits()
    window.current_page()._close_doc()     # a dead app holds no file open
    _crash(window)
    import os
    os.remove(src)
    dialogs.recovers.append(True)
    w = _new_window()
    try:
        assert w._current_key == "home"
        warned = dialogs.warnings()
        assert warned and "pages.pdf — Rotate & Reorder" in warned[-1][2]
        assert recovery.orphaned() == []
    finally:
        close_test_window(w)


@pytest.mark.parametrize("tool", ["AnnotateTool", "EditTextTool", "RedactTool"])
def test_every_document_workspace_offers_recovery(qapp, window, dialogs, tmp_path, tool):
    src = make_pdf(tmp_path / "w.pdf", pages=2)
    assert window.open_tool(tool, src)
    page = window.current_page()
    if tool == "RedactTool":
        page._pending.append((1, fitz.Rect(10, 10, 50, 50), None))
    else:
        page._dirty = True
    window.snapshot_edits()
    _crash(window)
    dialogs.recovers.append(True)
    w = _new_window()
    try:
        p = w.current_page()
        assert w._current_key == tool and p.is_dirty() and p.document_path() == src
        if tool == "RedactTool":
            assert [(pg, tuple(r)) for pg, r, _ in p._pending] == [(1, (10, 10, 50, 50))]
    finally:
        close_test_window(w)
