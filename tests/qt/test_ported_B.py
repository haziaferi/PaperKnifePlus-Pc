"""Behaviour the CTk tests in tests/test_enhance.py, tests/test_jobs.py and
tests/test_organise.py checked that no Qt or core test covered yet (phase 8
map B).  Each test names the CTk test it carries over."""
import re
import threading

import pymupdf as fitz

from qt_harness import image_pdf, make_pdf, pump, wait_job


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


# ── Compress ─────────────────────────────────────────────────────────────────
def test_compress_never_reports_a_negative_saving(window, dialogs, tmp_path):
    # CTk test_compress_never_reports_a_negative_saving
    from paperknife.qt.tools.compress import size_report
    role, status, title, text = size_report(1000 * 1024, 1200 * 1024, str(tmp_path / "o.pdf"))
    assert role == "warning"
    assert "smaller)" not in text and "%" not in status and "%" not in text, (status, text)
    # End to end on a file compression cannot shrink much.
    assert window.open_tool("CompressTool")
    pump(0.05)
    page = window.current_page()
    src = make_pdf(tmp_path / "in.pdf", pages=20)
    page.file.set_path(src)
    page.radios["medium"].setChecked(True)
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    said = " ".join(m[2] for m in dialogs.msgs) + " " + window.status_text()
    assert not re.search(r"[-−]\d+% smaller|\([-−][-−]", said), said
    if out.stat().st_size >= (tmp_path / "in.pdf").stat().st_size:
        assert "smaller)" not in said, said


def test_compress_page_can_overwrite_its_input(window, dialogs, tmp_path):
    # CTk test_compress_can_overwrite_its_input (the core test covers
    # core.compress_pdf; this one goes through the page and its job)
    assert window.open_tool("CompressTool")
    pump(0.05)
    page = window.current_page()
    src = image_pdf(tmp_path / "in.pdf")
    page.file.set_path(src)
    page.radios["medium"].setChecked(True)
    dialogs.save(src)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(src) as d:
        assert [img[2] for img in d[0].get_images(full=True)] == [625]
        assert "Searchable text 1" in d[0].get_text()
    assert not list(tmp_path.glob("*.part"))


# ── Jobs ─────────────────────────────────────────────────────────────────────
def test_find_all_returns_before_the_search_is_done(window, dialogs, tmp_path, monkeypatch):
    # CTk test_find_all_returns_before_the_search_is_done: the search runs in
    # a job, so the call returns at once and the hits arrive when it ends.
    from paperknife.core import text as core_text
    src = make_pdf(tmp_path / "in.pdf", pages=2, text="needle {n}")
    assert window.open_tool("FindReplaceTool", src)
    pump(0.05)
    page = window.current_page()
    release, finished = threading.Event(), threading.Event()
    real = core_text.find_all

    def slow_find_all(*a, **k):
        release.wait(3)
        try:
            return real(*a, **k)
        finally:
            finished.set()

    monkeypatch.setattr(core_text, "find_all", slow_find_all)
    page.find_edit.setText("needle")
    try:
        page.find_all()
        assert not finished.is_set(), "find_all waited for the search"
        assert window.job_running() and page._hits == []
    finally:
        release.set()
    wait_job(window)
    assert len(page._hits) == 2 and page.hit_label.text() == "Found 2 hit(s)"


def test_while_a_save_holds_the_document_the_window_cannot_reach_it(window, dialogs, tmp_path,
                                                                     monkeypatch):
    # CTk test_while_a_job_holds_the_document_the_window_cannot_reach_it
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    src = make_pdf(tmp_path / "a.pdf", pages=2)
    assert window.open_tool("AnnotateTool", src)
    pump(0.1)
    page = window.current_page()
    release = threading.Event()
    sd = window.document                # the window's Save writes it (2026-10-23)
    real_save = type(sd)._save_doc

    def slow_save(self, out, **kw):
        release.wait(20)
        return real_save(self, out, **kw)

    monkeypatch.setattr(type(sd), "_save_doc", slow_save)
    opened = []
    monkeypatch.setattr(page, "open", lambda: opened.append(1))
    dialogs.save(tmp_path / "out.pdf")
    window.save_as()
    try:
        assert window.is_locked()
        assert window.show_page("home") is False            # refused
        assert window.current_page() is page
        window.activateWindow()
        window.setFocus()
        pump(0.05)
        QTest.keyClick(window, Qt.Key_O, Qt.ControlModifier)
        pump(0.1)
        assert opened == [], "a shortcut reached the page while its document was in use"
        assert window.page_hook("open") is False
    finally:
        release.set()
    wait_job(window)
    assert not window.is_locked()
    assert (tmp_path / "out.pdf").exists()
    assert window.show_page("home") is True
    assert window._current_key == "home"


# ── Merge ────────────────────────────────────────────────────────────────────
def test_merge_row_click_selects_the_file_after_a_remove(window, tmp_path):
    # CTk test_merge_name_click_selects_the_file_after_a_remove
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    assert window.open_tool("MergeTool")
    pump(0.05)
    page = window.current_page()
    page.add_paths([make_pdf(tmp_path / f"{n}.pdf", pages=1) for n in "ABC"])
    pump(0.05)
    page.select(0)
    page.remove_btn.click()
    pump(0.05)
    row_b = page.rows[0]
    assert row_b.name_label.text() == "B.pdf"
    QTest.mouseClick(row_b.name_label, Qt.LeftButton)
    pump(0.05)
    assert page.selected_index() == 0
    page.remove_btn.click()
    pump(0.05)
    assert [r.name_label.text() for r in page.rows] == ["C.pdf"]
